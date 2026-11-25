# Webhooks

## Delivery
Quillfeather Dispatch retries a failed webhook delivery 8 times over 24 hours with exponential backoff. Each delivery is signed with an HMAC-SHA256 signature in the X-Quill-Signature header.

## Ordering
Webhook events for one route always arrive in order, while events across routes can interleave.
