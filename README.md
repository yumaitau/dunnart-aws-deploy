# KISS Company: deploy into your AWS account

One company workspace, licensed through an AWS Marketplace SaaS contract. Yuma operates the small licensing service; your application, database and Hermes profiles run in your AWS account.

**Pilot status:** source and installer are under validation. No installable release is published until its image digest and buyer entitlement flow have been verified. Do not treat a source checkout as a production release.

## Getting started

1. Accept your private Marketplace offer and choose **Set up your account**. Complete registration in the Yuma licensing service.
2. Open AWS CloudShell in the **subscribing account**, in **Sydney (`ap-southeast-2`)**.
3. Run the versioned command supplied with your release. The deployment prepares a generated HTTPS address and prints a private, expiring owner claim link.
4. Claim the owner account. Add a **dedicated Composio project key** in Settings, connect your own apps and invite teammates.

The release command downloads a tagged checkout and runs `./install.sh`. This repository intentionally does not advertise a working release tag before validation. To review infrastructure first, run `./install.sh --plan` from a published release. Planning prepares the encrypted, versioned S3 state bucket but does not create the application stack.

Run the same checkout again to resume a failed installation. Keep `terraform/installation.auto.tfvars.json`: it holds your non-secret installation identity. Do not invent a new ID when recovering an existing licensed workspace.

## Data and licensing

- Seller: subscription registration, verified buyer AWS account, registration email, installation binding and entitlement expiry. No chats, mailbox content, tasks or Composio credentials.
- Buyer: ECS Fargate web/worker/Hermes service, encrypted PostgreSQL RDS, EFS profiles, Secrets Manager and CloudWatch logs.
- Composio and your selected model provider process the connected content needed for your requests. Personal connections, conversations and accepted learning are user-scoped; work is shared only when explicitly selected.
- The task IAM role signs lease requests. Seller checks `GetEntitlements` and signs a short-lived response. Application verifies the embedded public key, product, installation, nonce and expiry. Seller credentials never enter buyer containers.
- Runtime enforcement is compiled into Marketplace builds. Environment flags cannot turn it off. Current leases last at most 20 minutes; cached checks refresh after 15 minutes. Missing or expired entitlement fails closed.
- Native tasks can be organised by the agent. Connected-app changes require exact human approval, including changes to linked native tasks.

The public deployment source and public image do not replace the software licence. A customer controls their own AWS environment; no application licence check can prevent an administrator from modifying software. Signed releases and the contract define the supported distribution.

## Infrastructure and cost

Pilot uses one ARM64 ECS task (1 vCPU, 4 GiB), three containers, single-AZ RDS PostgreSQL, EFS, one NAT gateway and a private ALB behind CloudFront VPC origin. This is a small deployment, not a high-availability configuration. Upgrades restart the service and briefly interrupt chat. Use Sydney; the default Bedrock inference profile can process in Sydney and Melbourne.

Marketplace licence, AWS infrastructure, Bedrock usage and Composio charges are separate. NAT, ALB and RDS accrue charges even while nobody is chatting. Review the Terraform plan and your AWS cost estimate before deployment. Model access/Anthropic use-case prerequisites must be completed in your AWS account.

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
