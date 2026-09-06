# Reporting something you have found

Departed is a dead man's switch. Its whole job is to hold something private until
one moment, so a hole in it matters more than the size of the project suggests.

**Please report privately first.** On GitHub, open the repository's Security tab
and choose *Report a vulnerability*. That reaches me without the details being
public. I will confirm I have it within a few days and tell you plainly whether I
can fix it and when.

If you would rather not use GitHub, the contact routes on
[departed.lightmorphic.com](https://departed.lightmorphic.com) reach the same
person.

## What is in scope

- Anything that lets one account read or change another's settings, files or log.
- Anything that lets an unauthenticated visitor past the sign-in, other than the
  check-in link, which is meant to be open and carries its own single-use token.
- Anything that causes the switch to fire early, or to fail to fire, or to report
  that it sent something it did not.
- Anything that could expose an archive passphrase, which is meant never to leave
  the browser it was made in.
- Weaknesses in the sealed archive format itself: AES-256-CBC with a key stretched
  by 600,000 rounds of PBKDF2-SHA256, in an OpenSSL-compatible container.

## What is not

- The app being reachable by anyone who is already on your network. It has no
  business on the open internet and says so; the sign-in is a second lock, not the
  first.
- The app launcher script loaded from `apps.lightmorphic.com`. It is a known and
  documented exception, named in the README.
- Anything that needs an attacker to already have root on the machine it runs on.
  At that point they have the encryption key file too, and the README says so.

## What you can expect

I am one person and this is free software, so there is no bounty and no service
level. What there is: an honest answer, a fix if I can write one, a plain note in
the changelog when it lands, and credit in the release unless you would rather not
have it.
