# Calibre-Web → eLM Reader Deep Link (setup)

Spec `013-calibre-reader-deeplink.md`. This makes Calibre-Web's **"Read in web
browser"** button open the book in **eLibrary Manager's reader** instead of
Calibre-Web's own reader — without forking Calibre-Web.

## How it works

```
Calibre-Web  ──GET /books/read/<calibre_id>──►  reverse proxy
                                                      │ rewrites to:
                                                      ▼
eLM  GET /calibre/launch?calibre_id=<calibre_id>  ──302──►  /reader/<elm_book_id>
```

* `calibre_id` is Calibre's numeric book id. eLM stores it on each imported book
  (`Book.calibre_id`, written by the spec-011 importer), so the mapping is an
  indexed lookup — no Calibre-Web modification needed.
* `/calibre/launch` is a normal page route, so an unauthenticated request is sent
  to `/login` (not a 401). Behind a shared domain, eLM's `SameSite=Lax` session
  cookie rides along on the redirect, so a logged-in admin lands straight in the
  reader.

## Prerequisites

1. **Import the Calibre library into eLM** at least once (Settings → Calibre →
   Import). Only imported books can be opened; an unimported id redirects to the
   library with a "run a Calibre import" notice.
2. **Both apps on one domain.** Shared cookie scope requires a single host. The
   recommended layout: eLM at the root, Calibre-Web under `/books`.

## Calibre-Web subpath

Calibre-Web must generate `/books/...` links so its own "Read" button points at
`/books/read/<id>`. In Calibre-Web admin (**Basic Configuration → Feature
Configuration**, or `app.db` settings) set the URL suffix / `APPLICATION_ROOT`
to `/books` (the exact field name varies by version — look for "URL prefix" /
"Reverse proxy"). Then its reader entrypoints become `/books/read/<id>` and
`/books/read/<id>/<format>`.

> **Verify first:** open Calibre-Web, hover the "Read in web browser" button,
> and read the actual `href`. Match the rewrite regex below to that path.
> Calibre-Web versions differ (`/read/<id>`, `/read/<id>/<fmt>`, `/readbook/<id>`).

## Caddy

```caddyfile
elib.local {
	# 1. Rewrite Calibre-Web's reader entrypoints to the eLM launch endpoint.
	@cw_read path_regexp cw_read ^/books/read(?:book)?/(\d+)(?:/.*)?$
	rewrite @cw_read /calibre/launch?calibre_id={re.cw_read.1}

	# 2. Everything else under /books/* → Calibre-Web (catalog/metadata/OPDS).
	@cw path /books/*
	reverse_proxy @cw_read 127.0.0.1:8083  # only matched above; harmless if repeated
	reverse_proxy @cw 127.0.0.1:8083 {
		header_up X-Forwarded-Proto {scheme}
	}

	# 3. Root (and everything else) → eLM: /calibre/launch, /reader/*, /api/*.
	reverse_proxy 127.0.0.1:8000 {
		header_up X-Forwarded-Proto {scheme}
	}
}
```

* `8083` = Calibre-Web, `8000` = eLM.
* `X-Forwarded-Proto` is required: eLM ties its `secure` session cookie to
  `request.url.scheme == "https"`. Without it behind a TLS-terminating proxy the
  cookie won't attach and the redirect will bounce to `/login`.

## nginx

```nginx
upstream elm        { server 127.0.0.1:8000; }
upstream calibre_web { server 127.0.0.1:8083; }

server {
    listen 443 ssl http2;
    server_name elib.local;

    # 1. Rewrite Calibre-Web's reader entrypoints to the eLM launch endpoint.
    location ~ ^/books/read(?:book)?/(\d+)(?:/.*)?$ {
        rewrite ^ /calibre/launch?calibre_id=$1 last;
    }

    # 2. Everything else under /books/* → Calibre-Web.
    location /books/ {
        proxy_pass http://calibre_web;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
    }

    # 3. Root → eLM.
    location / {
        proxy_pass http://elm;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
    }
}
```

Note the order: the regex `location` for `/books/read/...` is evaluated before
the prefix `location /books/`, so reader clicks are intercepted and everything
else under `/books/` reaches Calibre-Web untouched.

## Separate-domain deployments

If Calibre-Web and eLM **cannot** share one domain, the shared-cookie approach
does not apply. In that case use either:

* a proxy-level SSO in front of both (e.g. oauth2-proxy / Authelia), or
* the deferred **signed deep-link token** (spec 013 open item): eLM issues an
  HMAC-signed `?t=<sig>&exp=<ts>` over the Calibre id that `/calibre/launch`
  honors, embedded into Calibre-Web's Read link via a small template tweak.

## Verifying the deep link end-to-end

1. Confirm a book is imported (its card shows in eLM and was imported from
   Calibre).
2. In Calibre-Web, click **"Read in web browser"**.
3. Expected: the browser navigates to `https://elib.local/reader/<id>` and the
   eLM reader opens at that book.
4. For a book **not** imported: you land on the library with a "Calibre book not
   imported" notice.
5. For a **hidden** book: you land on the library with a "Book is hidden" notice
   (the reader is never opened).
