# Rate limits

## Defaults
The default limit is 600 requests per minute for each workspace. Route optimization calls count as 10 requests each because they run a solver.

## When you hit the limit
A request over the limit returns status 429 with a Retry-After header in seconds. Enterprise workspaces can raise the limit to 6,000 requests per minute from the console.
