#!/usr/bin/env python3
"""Generate a launch template pinned to a reviewed public deployment commit."""
import argparse, json, pathlib, re
root=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--commit',required=True);args=p.parse_args()
if not re.fullmatch('[a-f0-9]{40}',args.commit):p.error('Expected full Git commit')
ref=lambda name:{'Ref':name}
get=lambda name, attr='Arn':{'Fn::GetAtt':[name,attr]}
sub=lambda value:{'Fn::Sub':value}
role=lambda service,statements:{'Type':'AWS::IAM::Role','Properties':{'AssumeRolePolicyDocument':{'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Service':service},'Action':'sts:AssumeRole'}]},'Policies':[{'PolicyName':'LaunchCompany','PolicyDocument':{'Version':'2012-10-17','Statement':statements}}]}}
allow=lambda actions, resource='*':{'Effect':'Allow','Action':actions,'Resource':resource}
release=json.loads((root/'release.json').read_text())
api=release['licenseInvokeArn'].rsplit('/',1)[0]
# All deployment logic is downloaded at an immutable commit; no moving branch executes.
source=f'https://github.com/yumaitau/kiss-company-aws-deploy/archive/{args.commit}.tar.gz'
commands=['curl --fail --location --retry 3 '+source+' -o /tmp/company.tar.gz',
          'mkdir -p /tmp/company && tar -xzf /tmp/company.tar.gz --strip-components=1 -C /tmp/company',
          'bash /tmp/company/install.sh --automated']
buildspec=json.dumps({'version':'0.2','phases':{'build':{'commands':commands}}})
resources={
 'BuildLogs':{'Type':'AWS::Logs::LogGroup','Properties':{'RetentionInDays':14}},
 'BuildRole':role('codebuild.amazonaws.com',[
   allow(['ec2:*','ecs:*','rds:*','elasticfilesystem:*','elasticloadbalancing:*','cloudfront:*','s3:*','logs:*','secretsmanager:*','cloudwatch:*']),
   allow(['iam:CreateRole','iam:GetRole','iam:DeleteRole','iam:PutRolePolicy','iam:GetRolePolicy','iam:DeleteRolePolicy','iam:ListRolePolicies','iam:ListAttachedRolePolicies','iam:TagRole','iam:UntagRole','iam:ListInstanceProfilesForRole'],sub('arn:${AWS::Partition}:iam::${AWS::AccountId}:role/kiss-company-*')),
   {**allow(['iam:PassRole'],sub('arn:${AWS::Partition}:iam::${AWS::AccountId}:role/kiss-company-*')),'Condition':{'StringEquals':{'iam:PassedToService':'ecs-tasks.amazonaws.com'}}},
   {**allow(['iam:CreateServiceLinkedRole']),'Condition':{'StringEquals':{'iam:AWSServiceName':['ecs.amazonaws.com','elasticloadbalancing.amazonaws.com','rds.amazonaws.com','cloudfront.amazonaws.com','backup.amazonaws.com']}}},
   allow(['execute-api:Invoke'],[api+'/'+route for route in ['lease','deployment-status','connector-project']]),
 ]),
 'Build':{'Type':'AWS::CodeBuild::Project','Properties':{'ServiceRole':get('BuildRole'),'ConcurrentBuildLimit':1,'TimeoutInMinutes':120,'QueuedTimeoutInMinutes':30,'Artifacts':{'Type':'NO_ARTIFACTS'},'Source':{'Type':'NO_SOURCE','BuildSpec':buildspec},'Environment':{'Type':'LINUX_CONTAINER','ComputeType':'BUILD_GENERAL1_SMALL','Image':'aws/codebuild/standard:7.0','PrivilegedMode':False},'LogsConfig':{'CloudWatchLogs':{'Status':'ENABLED','GroupName':ref('BuildLogs')}}}},
 'ProviderRole':role('lambda.amazonaws.com',[allow(['codebuild:StartBuild'],get('Build'))]),
 'Provider':{'Type':'AWS::Lambda::Function','Properties':{'Runtime':'python3.13','Handler':'index.handler','Role':get('ProviderRole'),'Timeout':60,'Environment':{'Variables':{'PROJECT':ref('Build')}},'Code':{'ZipFile':(root/'scripts/launch-provider.py').read_text()}}},
 'Start':{'Type':'Custom::CompanyLaunch','Properties':{'ServiceToken':get('Provider'),'InstallationId':ref('InstallationId'),'OwnerClaimHash':ref('OwnerClaimHash')}}
}
template={'AWSTemplateFormatVersion':'2010-09-09','Description':'Launch your private KISS Company workspace. AWS infrastructure and AI usage billed separately. This stack creates the installer; company resources and data are retained separately in Terraform.',
 'Parameters':{'InstallationId':{'Type':'String','AllowedPattern':'[a-f0-9-]{36}','Description':'Prepared automatically by KISS Company. Leave unchanged.'},'OwnerClaimHash':{'Type':'String','AllowedPattern':'[a-f0-9]{64}','Description':'Protects your owner setup. Leave unchanged.'}},
 'Rules':{'Sydney':{'Assertions':[{'Assert':{'Fn::Equals':[ref('AWS::Region'),'ap-southeast-2']},'AssertDescription':'Launch this workspace in Sydney (ap-southeast-2).'}]}},
 'Resources':resources,'Outputs':{'SetupPage':{'Value':release['licenseUrl']+'/setup','Description':'Return here to watch setup and open your workspace.'},'BuildId':{'Value':get('Start','BuildId'),'Description':'Installer job. Stack completion means the installer started; workspace readiness appears on your setup page.'}}}
(root/'cloudformation/launch.template.json').write_text(json.dumps(template,indent=2)+'\n')
