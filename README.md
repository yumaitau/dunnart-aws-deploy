# KISS Company: deploy into your AWS account

One company workspace, licensed through an AWS Marketplace SaaS contract. Yuma operates the small licensing service; your application, database and Hermes profiles run in your AWS account.

**Pilot status:** a pinned pilot image and guided installer are published for validation. The buyer entitlement and deployment flow still need live proof. Do not treat a source checkout as a production release.

## Getting started

1. Subscribe through AWS Marketplace and choose **Set up your account**.
2. On the KISS Company setup page, choose **Launch my workspace**. AWS opens with everything filled in. Approve the installer permissions in the subscribing account.
3. Return to the setup page. It shows actual deployment progress and opens your workspace when ready.
4. Create your owner account, choose Gmail or Outlook, approve access and start chatting. No domain or Composio API key needed.

The private owner link stays in the browser where you started. Keep that browser tab available until you create your account. It expires after 24 hours. Contact Yuma support if setup needs recovery.

The CloudFormation stack starts a buyer-owned CodeBuild installer. **Stack completion means the installer started; the KISS setup page confirms when the workspace is ready.** The installer runs Terraform from an immutable deployment commit. Company resources and data are managed by Terraform separately: deleting the launcher does not remove them or stop their charges. Do not delete the launcher while its build is running.

### Advanced: command-line setup

The versioned release command runs `./install.sh` in AWS CloudShell in Sydney (`ap-southeast-2`). A supported release will be advertised after buyer validation; source checkouts are not a release. `./install.sh --plan` reviews infrastructure and prepares the state bucket. `--advanced-byo-connections` lets an experienced owner configure a dedicated Composio project later.

Rerunning resumes the installation using its identity and service state from encrypted buyer S3. Runtime secrets remain in Secrets Manager. Do not invent a new installation ID to recover an existing licensed workspace.

## Data and licensing

- Seller: subscription registration, verified buyer AWS account, registration email, installation binding, setup progress and entitlement expiry. Seller provisions an isolated Composio project and retains its project key in Secrets Manager. The buyer receives only its own project key. Chat and connected-app traffic are not proxied through the seller setup service.
- Buyer: ECS Fargate web/worker/Hermes service, encrypted PostgreSQL RDS, EFS profiles, Secrets Manager and CloudWatch logs.
- Composio and your selected model provider process the connected content needed for your requests. Personal connections, conversations and accepted learning are user-scoped; work is shared only when explicitly selected.
- The task IAM role signs lease requests. Seller checks `GetEntitlements` and signs a short-lived response. Application verifies the embedded public key, product, installation, nonce and expiry. Seller credentials never enter buyer containers.
- Runtime enforcement is compiled into Marketplace builds. Environment flags cannot turn it off. Current leases last at most 20 minutes; cached checks refresh after 15 minutes. Missing or expired entitlement fails closed.
- Native tasks can be organised by the agent. Connected-app changes require exact human approval, including changes to linked native tasks.

The public deployment source and public image do not replace the software licence. A customer controls their own AWS environment; no application licence check can prevent an administrator from modifying software. Signed releases and the contract define the supported distribution.

## Infrastructure and cost

Pilot uses one ARM64 ECS task (1 vCPU, 4 GiB), three containers, single-AZ RDS PostgreSQL, EFS, one NAT gateway and a private ALB behind CloudFront VPC origin. This is a small deployment, not a high-availability configuration. Upgrades restart the service and briefly interrupt chat. Use Sydney; the default Bedrock inference profile can process in Sydney and Melbourne.

AWS infrastructure and Bedrock usage are separate from the Marketplace licence. Managed connection allowances are specified in the offer; advanced BYO Composio usage is billed through your own account. NAT, ALB and RDS accrue charges even while nobody is chatting. Review the Terraform plan and your AWS cost estimate before deployment. Model access/Anthropic use-case prerequisites must be completed in your AWS account.

## Operations and recovery

Terraform state uses encrypted, versioned S3 with native lockfiles. Runtime encryption keys are created in Secrets Manager outside Terraform; never delete or replace them during upgrades. Restoring PostgreSQL without its original application encryption key makes stored connector credentials unreadable.

RDS automated backups retain seven days. EFS backup policy is enabled. Database deletion protection is on, and final snapshots are required. Secrets use a 30-day recovery window. Restore into an isolated installation first; verify login, stored credentials, tasks and profile access before moving traffic. **Restore/teardown has not yet been exercised in a buyer account.**

Do not run `terraform destroy` as a subscription-cancellation action. Cancelling stops licensed work; it does not delete your AWS infrastructure or stop its charges. Export and verify backups first. To decommission, explicitly disable database deletion protection, review the destroy plan and preserve required state, secrets and snapshots.

## Development checks

```sh
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform validate
python3 -m py_compile scripts/install.py
```

CloudShell needs an IAM principal able to provision the resources in Terraform and pass the generated ECS roles. Runtime permissions are separately scoped to the database secret, application secrets, the licence API, Bedrock and the EFS access point.
