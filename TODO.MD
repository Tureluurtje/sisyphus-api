# Project TODOs

- [ ] Add comments to all files/functions
- [ ] Add email verification
- [ ] Add security policy headers
- [ ] Add third party sign up/login (Google, Apple, GitHub)
- [ ] Implement GraphQL API endpoint/logic
- [ ] Add password reset endpoint
- [X] Add user deletion capability
- [ ] Add Redis bucket limiter
- [ ] Improve access token claims
- [ ] Add email rate limiting
- [ ] Fix PyJWT type stubs with correct versioning
- [ ] One "encrypted" cookie instead of three seperate ones(auth)
- [ ] Option to have wrong card only move back one
- [ ] Make refresh token expire x days after last use. Track user login for this(with access token) and update in db/session. Only for 1 session, check with sid in access token claims.
- [ ] Use sqlalchemy 2.0 style everywhere(db.filter() and db.execute)
