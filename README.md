# Custom Resource Lambda Handler

Contains all Sourced custom resource handler definitions.

* All cusotm resources must have the following attribute which informs cloudformation of the lambda to use:
  ServiceToken: !Ref 'CustomFunctionArn'

## Supported Custom Resources:
* ServiceControlPolicy
* ServiceControlPolicyAttachment
* OrganizationalUnit


## TODO
* Detacht the GrantAll default policy (always called p-FullAWSAccess) when attaching new policy (re attach it if there are no other policy upon policy attachment deletion, (list_policies_for_target) )
* When the account creation API works reliably implement OrganizationAccount
*Currently you must manually add or remove the default policy
### Return Values (Intrinsic Function Ref)

| Resource Type  | Reference Value | Example Return Value |
| ----            | --------------------- | --------------------------------------------------------|
| Custom::ServiceControlPolicy            |       Policy Id |  p-93udyd                             |
| Custom::ServiceControlPolicyAttachment  | Attachment Logical Resource Id |  SCPNonProdPolicytoOU      |
| Custom::OrganizationalUnit              |  Id           |  ou-akyid3                              |

### Attribuetes  (Intrinsic Function Fn::GetAtt)

| Resource Attribute   | Example Return Value |
| ----             | -------------------              |
| Custom::ServiceControlPolicy:Id                    |    p-8wu9e02d               |
| Custom::ServiceControlPolicy:Arn                   |  arn:aws:organizations::003422198502:policy/o-r2rjrevijr/service_control_policy/p-me305xlp         |
| Custom::ServiceControlPolicyAttachment |       No Attribuetes    |
| Custom::OrganizationalUnit:Arn         |                 arn:aws:organizations::003422198502:ou/o-r2rjrevijr/ou-3hbo-718f1jd9      |
| Custom::OrganizationalUnit:Id         |                 ou-3hbo-718f1jd9      |

### Input Parameters
#### ServiceControlPolicy

| Resource Attribute   |
Valid  Values | Comment |
| ----             | -------------------              | -------|
| PolicyName                    |    string           | Name of policy |
| PolicyDescription             |    string           | My policy     |
| Type                   |      SERVICE_CONTROL_POLICY    | Currently only SERVICE_CONTROL_POLICY is supported  |
| PolicyDocument                  | A valid SCP Policy Document            | See example.yml |

#### OrganizationalUnit

| Resource Attribute   | Valid  Values         |       Comment |
| ----                 | -------------------         | -------|
| Name                    |    string           | Name of policy |
| ParentId             |    string or special value "root"     | Can be an account id, an ou Id or root id if you provide "root" the first root from list_roots will be used in place     |

#### ServiceControlPolicyAttachment

| Resource Attribute   | Valid  Values         |       Comment |
| ----                 | -------------------         | -------|
| PolicyId             |    string           | Name of policy |
| TargetId             |    target account, 'root' or OU physicalid     | Can be an account id, an ou Id or root id if you provide "root" the first root from list_roots will be used in place     |



Given a Cloudformation event such as:

```
{
  "Records": [
    {
      "awsRegion": "ap-southeast-1",
      "codecommit": {
        "references": [
          {
            "commit": "268cec620cdca47f51ee0a92a85b355a49fc90d2",
            "ref": "refs/heads/client_setup"
          }
        ]
      },
      "eventId": "11ef9957-dd35-4a4d-890f-a4f766683345",
      "eventName": "ReferenceChanges",
      "eventPartNumber": 1,
      "eventSource": "aws:codecommit",
      "eventSourceARN": "arn:aws:codecommit:ap-southeast-1:CHANGEME:core-billing",
      "eventTime": "2017-12-06T06:23:18.171+0000",
      "eventTotalParts": 1,
      "eventTriggerConfigId": "7c24c9fd-7b69-43e3-9c28-e949d7bc69aa",
      "eventTriggerName": "MyTestTrigger",
      "eventVersion": "1.0",
      "userIdentityARN": "arn:aws:sts::CHANGEME:assumed-role/OrganizationAccountAccessRole/AWS-CLI-session-123"
    }
  ]
}
```

* Example Cloudformation to Create a ServiceControlPolicy and attach it to an OU

```
  CustomResource:
    Type: Custom::ServiceControlPolicy
    Properties:
      ServiceToken: !Ref 'CustomFunctionArn'
      PolicyName: ABRENTSTACK22
      PolicyDescription: "PolicyDescriptionTest"
      Type: "SERVICE_CONTROL_POLICY"
      PolicyDocument:
        Version: "2012-10-17"
        Statement:
           -  Effect: Deny
              Resource: "*"
              Action:
                - cloudtrail:DeleteTrail
                - cloudtrail:StopLogging
           -  Effect: Allow
              Resource: "*"
              Action:
                - athena:*

  OUNonProd:
    Type: Custom::OrganizationalUnit
    Properties:
      ServiceToken: !Ref 'CustomFunctionArn'
      ParentId: root
      Name: ServicesOU22
      Children:
        - Accoundid1
        - Accountid2

  AttachmentAutomation:
    Type: Custom::ServiceControlPolicyAttachment
    Properties:
      ServiceToken: !Ref 'CustomFunctionArn'
      PolicyId: !Ref 'CustomResource2'
      TargetId: "003422198502"
```
