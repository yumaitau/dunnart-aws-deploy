"""Start a buyer-owned build. CloudFormation tracks the launcher, not company data."""
import hashlib, json, os, urllib.request
import boto3

def handler(event, context):
    status, data = 'SUCCESS', {}
    try:
        if event['RequestType'] != 'Delete':
            props = event['ResourceProperties']
            result = boto3.client('codebuild').start_build(
                projectName=os.environ['PROJECT'],
                idempotencyToken=hashlib.sha256(event['RequestId'].encode()).hexdigest(),
                environmentVariablesOverride=[
                    {'name':'KISS_INSTALLATION_ID','value':props['InstallationId'],'type':'PLAINTEXT'},
                    {'name':'OWNER_CLAIM_HASH','value':props['OwnerClaimHash'],'type':'PLAINTEXT'},
                ])
            data = {'BuildId':result['build']['id']}
    except Exception:
        status = 'FAILED'
    # Never log the event: it contains a private CloudFormation response URL.
    body = json.dumps({'Status':status, 'Reason':'Launcher started. Return to KISS Company for workspace progress.' if status == 'SUCCESS' else 'Could not start setup. Check the launcher permissions.',
        'PhysicalResourceId':event.get('PhysicalResourceId', 'kiss-company-launcher'),
        'StackId':event['StackId'], 'RequestId':event['RequestId'],
        'LogicalResourceId':event['LogicalResourceId'], 'Data':data}).encode()
    request = urllib.request.Request(event['ResponseURL'],data=body,headers={'Content-Type':''},method='PUT')
    with urllib.request.urlopen(request, timeout=20): pass
