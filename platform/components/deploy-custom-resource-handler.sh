#!/bin/bash
# Deploy the Custom resource handler.
# You must change the export command to the master account
# This ensured that Organizations actions will work

# Don't stop on error.
# set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

function usage {
  echo "Usage: deploy.sh <client> <branch> <build>"
}

CLIENT=$1
[ "$CLIENT" = "" ] && usage && exit 1

BRANCH=$2
[ "$BRANCH" = "" ] && usage && exit 1

BUILD=$3
[ "$BUILD" = "" ] && usage && exit 1

# Load client-specific vars from a standard location.
CLIENT_CONFIG_DIR="$DIR/../../$CLIENT-config"
source "$CLIENT_CONFIG_DIR/client-vars.sh"

# Confirm required vars are loaded.
[ "$CLIENT_NAME" = "" ] && client_vars && exit 1

echo "CLIENT_NAME=${CLIENT_NAME}, CLIENT_REGION=${CLIENT_REGION}, MASTER_REGION=${MASTER_REGION}, AUTOMATION_ACCOUNT=${AUTOMATION_ACCOUNT}"
AUTOMATION_BUCKET_NAME="$CLIENT_NAME-core-automation-$CLIENT_REGION"
ARTEFACTS_S3_PREFIX="artefacts/core/custom-resource-handler/$BRANCH/$BUILD"

# Lambda definitions

CFNHANDLER_FUNCTION_NAME="cfn_custom_resource_handler"
CFNHANDLER_ACCOUNT=$AUTOMATION_ACCOUNT
CFNHANDLER_CODE_BUCKET=$AUTOMATION_BUCKET_NAME
CFNHANDLER_STACK_NAME="core-automation-cfn-crh"

function package() {
  LAMBDA_FUNCTION_NAME=$1
  BUCKET_NAME=$2

  echo "Packaging Lambda function $LAMBDA_FUNCTION_NAME"
  cd $DIR/../lambdas/$LAMBDA_FUNCTION_NAME
  PACKAGE_NAME=lambda-$LAMBDA_FUNCTION_NAME.zip
  PACKAGE_PATH="/tmp/packages/$PACKAGE_NAME"
  PACKAGE_S3_PATH="$BUCKET_NAME/$ARTEFACTS_S3_PREFIX/$PACKAGE_NAME"
  1>/dev/null zip -9 -r $PACKAGE_PATH * -x \*.pyc \*.md \*.zip \*.log \*__pycache__\* \*.so
}


# Package and upload the Cloudformation Custom Resource Handler Lambda function
rm -rf /tmp/packages
mkdir -p /tmp/packages
for LAMBDA_FUNCTION_NAME in $CFNHANDLER_FUNCTION_NAME; do
  package $LAMBDA_FUNCTION_NAME $CFNHANDLER_CODE_BUCKET
done
echo "Uploading SCP CFN Lambda functions to s3://$BUCKET_NAME/$ARTEFACTS_S3_PREFIX/"
aws --profile $CLIENT_NAME-automation s3 --region $MASTER_REGION cp /tmp/packages s3://$BUCKET_NAME/$ARTEFACTS_S3_PREFIX/ --recursive --sse AES256

# Cleanup
rm -rf /tmp/packages

# Upload CloudFormation templates
echo "Uploading CloudFormation templates to $AUTOMATION_BUCKET_NAME/$ARTEFACTS_S3_PREFIX"
aws --profile $CLIENT_NAME-automation s3 --region $CLIENT_REGION cp $DIR/../cloudformation s3://$AUTOMATION_BUCKET_NAME/$ARTEFACTS_S3_PREFIX --recursive --sse AES256

AWS_PROFILE=$CLIENT_NAME-master
# Deploy the CFN custom resource handler stack
STACK_ACTION=update-stack
>/dev/null 2>&1 aws --region $CLIENT_REGION cloudformation describe-stacks --stack-name "$CFNHANDLER_STACK_NAME" || STACK_ACTION=create-stack
echo "Performing $STACK_ACTION on stack $CFNHANDLER_STACK_NAME"
aws  --profile $CLIENT_NAME-master cloudformation $STACK_ACTION \
  --region $CLIENT_REGION \
  --stack-name "$CFNHANDLER_STACK_NAME" \
  --template-url "https://s3-$CLIENT_REGION.amazonaws.com/$AUTOMATION_BUCKET_NAME/$ARTEFACTS_S3_PREFIX/cfn-custom-resource-handler.yaml" \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameters \
    "ParameterKey=LambdaCodeS3Bucket,ParameterValue=$CFNHANDLER_CODE_BUCKET" \
    "ParameterKey=LambdaCodeS3KeyPrefix,ParameterValue=$ARTEFACTS_S3_PREFIX" \
    "ParameterKey=LambdaFunctionNamePrefix,ParameterValue=core-automation-$BRANCH-$BUILD" \
  --output text
