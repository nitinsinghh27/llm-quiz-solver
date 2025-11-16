# AWS Elastic Beanstalk Deployment Guide

## Prerequisites

1. AWS Account (free tier eligible)
2. AWS CLI installed
3. EB CLI installed

## Step 1: Install AWS CLI

```bash
# macOS
brew install awscli

# Or download from: https://aws.amazon.com/cli/
```

## Step 2: Install EB CLI

```bash
pip install awsebcli
```

## Step 3: Configure AWS Credentials

1. Go to: https://console.aws.amazon.com/
2. Sign in or create account
3. Go to: IAM → Users → Your User → Security Credentials
4. Create Access Key
5. Save Access Key ID and Secret Access Key

Configure locally:

```bash
aws configure
# Enter:
# - AWS Access Key ID
# - AWS Secret Access Key
# - Default region: us-east-1
# - Default output format: json
```

## Step 4: Initialize Elastic Beanstalk

```bash
cd /Users/nitin/iitm-Projects/TDS/Project2

# Initialize EB
eb init

# Select:
# - Region: 1) us-east-1 (or closest to you)
# - Application name: llm-quiz-solver
# - Platform: Python
# - Platform version: Python 3.11
# - SSH: No (unless you want it)
```

## Step 5: Create Environment

```bash
# Create environment (this deploys your app)
eb create llm-quiz-solver-env

# This will:
# - Create an EC2 instance
# - Install dependencies
# - Start your Flask app
# - Give you a URL
```

## Step 6: Set Environment Variables

```bash
# Set your environment variables
eb setenv SECRET="dracarys" \
  EMAIL="23f3004206@ds.study.iitm.ac.in" \
  AIPIPE_API_KEY="eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjIzZjMwMDQyMDZAZHMuc3R1ZHkuaWl0bS5hYy5pbiJ9.QU4eoSXkpg1Mt9wr5IEjpkzGQZDe-UzSQ-8sI9eKAFg" \
  AIPIPE_BASE_URL="https://api.aipipe.ai/v1"
```

## Step 7: Get Your URL

```bash
eb status

# Look for "CNAME:" - that's your URL
# Example: llm-quiz-solver-env.us-east-1.elasticbeanstalk.com
```

## Step 8: Test Your Deployment

```bash
# Health check
curl https://YOUR-URL.elasticbeanstalk.com/health

# Quiz test
curl -X POST https://YOUR-URL.elasticbeanstalk.com/quiz \
  -H "Content-Type: application/json" \
  -d '{
    "email": "23f3004206@ds.study.iitm.ac.in",
    "secret": "dracarys",
    "url": "https://tds-llm-analysis.s-anand.net/demo"
  }'
```

## Updating Your App

After making code changes:

```bash
# Deploy updates
git add .
git commit -m "Your changes"
eb deploy
```

## Monitoring

```bash
# View logs
eb logs

# Open in browser
eb open

# Check health
eb health
```

## AWS Console (Alternative Method)

If CLI doesn't work, use the web console:

1. Go to: https://console.aws.amazon.com/elasticbeanstalk/
2. Click "Create Application"
3. Fill in:
   - **Application name**: llm-quiz-solver
   - **Platform**: Python
   - **Platform branch**: Python 3.11
   - **Application code**: Upload your code (zip Project2 folder)
4. Click "Configure more options"
5. **Software** → Environment properties:
   - Add: SECRET, EMAIL, AIPIPE_API_KEY, AIPIPE_BASE_URL
6. Click "Create application"

## Cost

AWS Free Tier includes:
- ✅ 750 hours/month of t2.micro EC2 instance (12 months)
- ✅ 5GB of S3 storage
- ✅ Should be **completely free** for 12 months

After 12 months: ~$15-20/month

## Troubleshooting

### Issue: "eb: command not found"
```bash
pip install awsebcli --upgrade
```

### Issue: Deployment fails
```bash
# Check logs
eb logs

# Common fix: ensure requirements.txt is correct
```

### Issue: App doesn't start
```bash
# Make sure app.py has:
if __name__ == '__main__':
    app.run()
```

### Issue: Timeout
```bash
# Increase timeout in .ebextensions/02_python.config
```

## Quick Deploy Script

Save this as `deploy_aws.sh`:

```bash
#!/bin/bash

echo "Deploying to AWS Elastic Beanstalk..."

# Commit latest changes
git add .
git commit -m "Deploy to AWS EB" || true

# Deploy
eb deploy

# Show status
eb status

echo "Done! Check your URL above."
```

Make it executable:
```bash
chmod +x deploy_aws.sh
./deploy_aws.sh
```

## Cleanup (After Evaluation)

To avoid charges after free tier:

```bash
# Terminate environment
eb terminate llm-quiz-solver-env

# Or in console: Delete application
```

## Support

- AWS Support: https://console.aws.amazon.com/support/
- EB Docs: https://docs.aws.amazon.com/elasticbeanstalk/
- Free Tier: https://aws.amazon.com/free/
