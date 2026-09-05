#!/usr/bin/env python3
"""Resumable CloudShell deployment. Secrets stay in memory and Secrets Manager."""
import argparse, base64, datetime, hashlib, hmac, json, os, pathlib, platform, secrets, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error, urllib.parse, uuid, zipfile
ROOT = pathlib.Path(__file__).resolve().parents[1]
REGION = 'ap-southeast-2'

def aws(service, operation, payload=None, region=REGION):
    import boto3
    # AWS CLI refreshes login/CloudShell credentials; SDK sends payloads without files or argv secrets.
    credentials=json.loads(subprocess.check_output(['aws','configure','export-credentials','--format','process'],text=True))
    client=boto3.client('s3' if service=='s3api' else service,region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials.get('SessionToken'))
    try:
        return getattr(client,operation.replace('-','_'))(**(payload or {}))
    except Exception:
        raise RuntimeError(f'AWS {service} {operation} failed. Check current account permissions and CloudWatch for this installation.') from None

def terraform():
    if shutil.which('terraform'):
        return shutil.which('terraform')
    version = '1.15.8'
    arch = {'aarch64':'arm64', 'arm64':'arm64', 'x86_64':'amd64'}[platform.machine()]
    system = platform.system().lower()
    name = f'terraform_{version}_{system}_{arch}.zip'
    base = f'https://releases.hashicorp.com/terraform/{version}/'
    archive = urllib.request.urlopen(base + name, timeout=60).read()
    sums = urllib.request.urlopen(base + f'terraform_{version}_SHA256SUMS', timeout=30).read().decode()
    expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == name)
    if hashlib.sha256(archive).hexdigest() != expected:
        raise RuntimeError('Terraform archive checksum mismatch')
    target = ROOT / '.tools'; target.mkdir(exist_ok=True)
    with tempfile.TemporaryFile() as f:
        f.write(archive); f.seek(0)
        with zipfile.ZipFile(f) as z:
            (target / 'terraform').write_bytes(z.read('terraform'))
    (target / 'terraform').chmod(0o700)
    return str(target / 'terraform')

def signed_request(release, path, payload):
    credentials = json.loads(subprocess.check_output(['aws','configure','export-credentials','--format','process'], text=True))
    body = json.dumps(payload, separators=(',',':')).encode()
    url = urllib.parse.urlsplit(release['licenseUrl']+path)
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp, day = now.strftime('%Y%m%dT%H%M%SZ'), now.strftime('%Y%m%d')
    headers = {'content-type':'application/json','host':url.netloc,'x-amz-date':stamp}
    if credentials.get('SessionToken'): headers['x-amz-security-token'] = credentials['SessionToken']
    names = ';'.join(sorted(headers))
    canonical = '\n'.join(['POST',url.path,'',''.join(f'{name}:{headers[name]}\n' for name in sorted(headers)),names,hashlib.sha256(body).hexdigest()])
    scope = f"{day}/{release['licenseRegion']}/execute-api/aws4_request"
    to_sign = '\n'.join(['AWS4-HMAC-SHA256',stamp,scope,hashlib.sha256(canonical.encode()).hexdigest()])
    key = ('AWS4'+credentials['SecretAccessKey']).encode()
    for part in [day,release['licenseRegion'],'execute-api','aws4_request']:
        key = hmac.new(key,part.encode(),hashlib.sha256).digest()
    signature = hmac.new(key,to_sign.encode(),hashlib.sha256).hexdigest()
    headers['Authorization'] = f"AWS4-HMAC-SHA256 Credential={credentials['AccessKeyId']}/{scope}, SignedHeaders={names}, Signature={signature}"
    try:
        request=urllib.request.Request(release['licenseUrl']+path, data=body, headers=headers, method='POST')
        with urllib.request.urlopen(request,timeout=30) as response: signed=json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'KISS Company setup request failed ({error.code}). Check the subscription or contact Yuma support.') from None
    return signed

def check_license(release, installation, account):
    nonce=str(uuid.uuid4())
    signed=signed_request(release,'/lease',{'installation':installation,'nonce':nonce})
    with tempfile.TemporaryDirectory() as directory:
        directory=pathlib.Path(directory)
        (directory/'key.pem').write_text(release['publicKey'])
        (directory/'signature').write_bytes(base64.b64decode(signed['signature'],validate=True))
        verification=subprocess.run(['openssl','dgst','-sha256','-verify',str(directory/'key.pem'),'-signature',str(directory/'signature'),'-sigopt','rsa_padding_mode:pss','-sigopt','rsa_pss_saltlen:32'],input=signed['payload'].encode(),capture_output=True)
        if verification.returncode: raise RuntimeError('Invalid seller licence signature')
    lease=json.loads(signed['payload'])
    expected={'account':account,'installation':installation,'nonce':nonce,'product':release['productCode'],'dimension':'company_workspace'}
    if any(lease.get(k)!=v for k,v in expected.items()) or not time.time()<lease.get('expires',0)<=time.time()+1200:
        raise RuntimeError('Invalid seller licence claims')
    print('Marketplace entitlement verified.',flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='Prepare state and show infrastructure plan only')
    parser.add_argument('--automated', action='store_true', help='Run behind the guided launch page; never print owner secrets')
    parser.add_argument('--advanced-byo-connections', action='store_true', help='Advanced: supply a dedicated Composio key later')
    args = parser.parse_args()
    release = json.loads((ROOT / 'release.json').read_text())
    image = release.get('image', '')
    if '@sha256:' not in image or len(image.rsplit(':',1)[1]) != 64:
        raise RuntimeError('Release has no verified image digest. This source checkout is not an installable release yet.')
    identity = aws('sts', 'get-caller-identity')
    account = identity['Account']
    print(f'Installing KISS Company in AWS account {account}, {REGION}. AWS infrastructure and AI usage billed separately.', flush=True)
    config_file = ROOT / 'terraform' / 'installation.auto.tfvars.json'
    if config_file.exists():
        config = json.loads(config_file.read_text())
        if config['buyer_account'] != account:
            raise RuntimeError('This checkout belongs to another AWS account; use a fresh checkout.')
    else:
        config = {'region':REGION, 'buyer_account':account, 'installation_id':os.environ.get('KISS_INSTALLATION_ID') or str(uuid.uuid4()), 'name':'kiss-company', 'enable_service':False}
    bucket = f'kiss-company-state-{account}-{REGION}'
    # Recover persisted identity before requesting a lease or changing infrastructure.
    try:
        aws('s3api','head-bucket',{'Bucket':bucket, 'ExpectedBucketOwner':account})
        existing=aws('s3api','list-objects-v2',{'Bucket':bucket,'Prefix':'company/installation.json','MaxKeys':1})
    except RuntimeError:
        existing={}
    if any(item['Key']=='company/installation.json' for item in existing.get('Contents',[])):
        subprocess.check_call(['aws','s3','cp',f's3://{bucket}/company/installation.json',str(config_file),'--only-show-errors'])
        saved=json.loads(config_file.read_text())
        requested=os.environ.get('KISS_INSTALLATION_ID')
        if saved['buyer_account']!=account or (requested and saved['installation_id']!=requested):
            raise RuntimeError('Existing company has a different installation identity')
        config=saved
    config.update(container_image=image, license_invoke_arn=release['licenseInvokeArn'])
    if args.automated and not os.environ.get('OWNER_CLAIM_HASH'): raise RuntimeError('Owner browser setup missing')
    config_file.write_text(json.dumps(config, indent=2)+'\n'); config_file.chmod(0o600)
    connector_key=''
    if not args.plan:
        check_license(release,config['installation_id'],account)
        if not args.advanced_byo_connections:
            connector_key=signed_request(release,'/connector-project',{'installation':config['installation_id']})['api_key']
    def progress(phase,url=None):
        if args.automated:
            signed_request(release,'/deployment-status',{'installation':config['installation_id'],'phase':phase,**({'workspace_url':url} if url else {})})
    progress('preparing')
    try:
        aws('s3api','head-bucket',{'Bucket':bucket, 'ExpectedBucketOwner':account})
    except RuntimeError:
        aws('s3api','create-bucket',{'Bucket':bucket,'CreateBucketConfiguration':{'LocationConstraint':REGION}})
    aws('s3api','put-public-access-block',{'Bucket':bucket,'PublicAccessBlockConfiguration':dict.fromkeys(['BlockPublicAcls','IgnorePublicAcls','BlockPublicPolicy','RestrictPublicBuckets'], True)})
    aws('s3api','put-bucket-versioning',{'Bucket':bucket,'VersioningConfiguration':{'Status':'Enabled'}})
    aws('s3api','put-bucket-encryption',{'Bucket':bucket,'ServerSideEncryptionConfiguration':{'Rules':[{'ApplyServerSideEncryptionByDefault':{'SSEAlgorithm':'AES256'}}]}})
    def save_config():
        config_file.write_text(json.dumps(config,indent=2)+'\n')
        subprocess.check_call(['aws','s3','cp',str(config_file),f's3://{bucket}/company/installation.json','--only-show-errors'])
    save_config()
    executable = terraform()
    def tf(*arguments, capture=False):
        return subprocess.check_output([executable, f'-chdir={ROOT / "terraform"}', *arguments], text=True) if capture else subprocess.check_call([executable, f'-chdir={ROOT / "terraform"}', *arguments])
    tf('init','-input=false',f'-backend-config=bucket={bucket}', '-backend-config=key=company/terraform.tfstate',f'-backend-config=region={REGION}','-backend-config=encrypt=true','-backend-config=use_lockfile=true')
    if args.plan:
        tf('plan','-input=false'); return
    progress('installing')
    tf('apply','-auto-approve','-input=false')
    outputs = {key:value['value'] for key,value in json.loads(tf('output','-json',capture=True)).items()}
    secret = aws('secretsmanager','describe-secret',{'SecretId':outputs['runtime_secret_arn']})
    if not any('AWSCURRENT' in stages for stages in secret.get('VersionIdsToStages',{}).values()):
        values = {key:base64.b64encode(secrets.token_bytes(32)).decode() for key in ['BETTER_AUTH_SECRET','APP_ENCRYPTION_KEY','HERMES_MANAGER_TOKEN']}
        values['COMPOSIO_API_KEY']=connector_key
        aws('secretsmanager','put-secret-value',{'SecretId':outputs['runtime_secret_arn'],'SecretString':json.dumps(values)})
    elif connector_key:
        values=json.loads(aws('secretsmanager','get-secret-value',{'SecretId':outputs['runtime_secret_arn']})['SecretString'])
        if not values.get('COMPOSIO_API_KEY'):
            values['COMPOSIO_API_KEY']=connector_key
            aws('secretsmanager','put-secret-value',{'SecretId':outputs['runtime_secret_arn'],'SecretString':json.dumps(values)})
    network = {'awsvpcConfiguration':{'subnets':outputs['subnets'],'securityGroups':[outputs['security_group']],'assignPublicIp':'DISABLED'}}
    # Use a dedicated one-container task, preventing a worker from starting before migrations.
    original = aws('ecs','describe-task-definition',{'taskDefinition':outputs['task_definition']})['taskDefinition']
    allowed = ['taskRoleArn','executionRoleArn','networkMode','volumes','requiresCompatibilities','cpu','memory','runtimePlatform']
    setup = {key:original[key] for key in allowed if key in original}
    setup['family'] = config['name']+'-setup'
    web = next(c for c in original['containerDefinitions'] if c['name']=='web')
    web['command'] = ['node','dist/migrate.js']; web.pop('portMappings',None)
    if os.environ.get('OWNER_CLAIM_HASH'):
        web['environment'].append({'name':'OWNER_CLAIM_HASH','value':os.environ['OWNER_CLAIM_HASH']})
    setup['containerDefinitions'] = [web]
    migration = aws('ecs','register-task-definition',setup)['taskDefinition']['taskDefinitionArn']
    def job(command):
        result = aws('ecs','run-task',{'cluster':outputs['cluster'],'taskDefinition':migration,'launchType':'FARGATE','networkConfiguration':network,'overrides':{'containerOverrides':[{'name':'web','command':command}]}})
        if result.get('failures') or not result.get('tasks'): raise RuntimeError('Setup task could not start')
        task = result['tasks'][0]['taskArn']
        deadline=time.monotonic()+900
        while time.monotonic()<deadline:
            status=aws('ecs','describe-tasks',{'cluster':outputs['cluster'],'tasks':[task]})['tasks'][0]
            if status['lastStatus']=='STOPPED':
                if any(c.get('exitCode') != 0 for c in status['containers']):
                    raise RuntimeError(f'Setup task failed: {task}. Check its CloudWatch logs; no service enabled.')
                return
            time.sleep(5)
        raise RuntimeError(f'Setup task timed out: {task}')
    job(['node','dist/migrate.js'])
    progress('connecting')
    job(['node','dist/setup-integrations.js'])
    if not config['enable_service']:
        job(['node','dist/bootstrap.js'])
    config['enable_service']=True
    save_config()
    progress('starting')
    tf('apply','-auto-approve','-input=false')
    deadline=time.monotonic()+900
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen(outputs['url']+'/api/health',timeout=10) as response:
                if response.status==200: break
        except Exception: pass
        time.sleep(5)
    else: raise RuntimeError('HTTPS health did not become ready. Rerun after checking ECS events.')
    progress('ready',outputs['url'])
    print('\nCompany ready: '+outputs['url'])
    (ROOT / '.kiss-result.json').write_text(json.dumps({'url':outputs['url']}))
    if args.automated:
        print('Return to your KISS Company setup page to finish.'); return
    try:
        claim=json.loads(aws('secretsmanager','get-secret-value',{'SecretId':outputs['claim_secret_arn']})['SecretString'])
        print('Private owner claim link (30-minute expiry; do not share):\n'+claim['url'])
    except RuntimeError:
        print('Existing company: sign in with your owner account.')

if __name__=='__main__':
    try: main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error),file=sys.stderr); sys.exit(1)
