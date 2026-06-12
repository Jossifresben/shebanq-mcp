# ---- Build stage: Emdros from source + BHSA SQLite DB ----
FROM python:3.11-slim-bookworm AS builder

ENV EMDROS_TAG=rel-3-9-0
# Pinned ETCBC commit, NOT master — makes the DB build reproducible.
ARG BHSA_REF=4db00e2157915495e1a4d3d57e41223df24775da
ENV MQL_URL=https://github.com/ETCBC/bhsa/raw/${BHSA_REF}/shebanq/2021/shebanq_etcbc2021.mql.bz2

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3-dev swig \
        autoconf automake libtool gettext pkg-config \
        re2c bison flex libpcre3-dev libsqlite3-dev bzip2 zip unzip wget ca-certificates \
        imagemagick graphviz \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN wget --tries=3 --timeout=30 -O emdros.tar.gz \
        "https://github.com/emdros/emdros/archive/refs/tags/${EMDROS_TAG}.tar.gz" \
    && tar xzf emdros.tar.gz

WORKDIR /build/emdros-${EMDROS_TAG}
RUN ( [ -f autogen.sh ] && sh autogen.sh ) || autoreconf -fi
RUN ./configure --prefix=/usr/local \
        --with-sqlite3=yes --with-mysql=no --with-postgresql=no --with-wx=no \
        --with-swig-language-python3=yes --with-swig-language-python2=no \
        --with-swig-language-java=no --with-swig-language-csharp=no \
        --with-swig-language-php7=no --disable-debug
# Drop the LaTeX doc subdir and stub pdflatex (same recipe as CI).
RUN sed -i -E 's/^(SUBDIRS *= *)doc /\1/' Makefile \
    && printf '%s\n' '#!/bin/sh' \
        'for a in "$@"; do case "$a" in *.tex) : > "${a%.tex}.pdf";; esac; done' \
        'exit 0' > /usr/local/bin/pdflatex \
    && chmod +x /usr/local/bin/pdflatex
RUN make -j"$(nproc)" && make install && ldconfig

# Build the BHSA SQLite DB. The dump's CREATE DATABASE names the file
# internally, so relocate if mql did not write the -d path.
WORKDIR /build/db
RUN wget -q -O bhsa.mql.bz2 "$MQL_URL" \
    && bunzip2 -kf bhsa.mql.bz2 \
    && /usr/local/bin/mql --backend sqlite3 -d bhsa.sqlite3 bhsa.mql \
    && if [ ! -s bhsa.sqlite3 ]; then \
         mv "$(find . -maxdepth 1 -name 'shebanq_etcbc2021*' ! -name '*.mql*' | head -1)" bhsa.sqlite3; \
       fi \
    && test -s bhsa.sqlite3

# Stage exactly the runtime libs the Python binding needs (closure via ldd).
# Copy the emdros shared libs by glob so each soname symlink AND its real
# target file both come across (a bare `cp -a` of an ldd-resolved soname copies
# only the dangling symlink). The ldd closure then sweeps up any remaining
# /usr/local deps, dereferencing with -L so no link is left pointing at nothing.
RUN mkdir -p /stage/lib/emdros \
    && cp -a /usr/local/lib/emdros/. /stage/lib/emdros/ \
    && cp -a /usr/local/lib/libemdros*.so* /stage/lib/ \
    && ldd /usr/local/lib/emdros/_EmdrosPy3.so \
        | awk '/=> \/usr\/local/ {print $3}' \
        | xargs -r -I{} cp -aL {} /stage/lib/

# ---- Runtime stage: slim, non-root, read-only DB ----
FROM python:3.11-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libsqlite3-0 libpcre3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

COPY --from=builder /stage/lib/ /usr/local/lib/
RUN ldconfig
ENV PYTHONPATH=/usr/local/lib/emdros
ENV LD_LIBRARY_PATH=/usr/local/lib
ENV SQLITE_TMPDIR=/tmp
RUN python -c "import EmdrosPy3; print('emdros import ok')"

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# The built web app, served when WEB_API=on (unused on the MCP service):
# the main page, the about page, and the Open Graph share image.
COPY demo/index.html /app/demo/index.html
COPY demo/about.html /app/demo/about.html
COPY demo/og.png /app/demo/og.png

# Read-only database: file 444, directory 555 (not writable by appuser).
COPY --from=builder /build/db/bhsa.sqlite3 /app/data/bhsa.sqlite3
RUN chmod 0444 /app/data/bhsa.sqlite3 && chmod 0555 /app/data

ENV BHSA_SQLITE=/app/data/bhsa.sqlite3
ENV LLM_PROVIDER=none
ENV MCP_TRANSPORT=http
ENV PORT=8000

USER appuser
# Build-time read-only self-test: prove appuser can query a 444 DB in a 555 dir
# (catches the "Emdros wants a writable handle" failure the design flags).
RUN python -c "from shebanq_mcp.server import _run_startup_selftest; \
import sys; sys.exit(0 if _run_startup_selftest() else 1)"

EXPOSE 8000
CMD ["shebanq-mcp"]
