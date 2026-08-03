FROM python:3.14-bookworm
LABEL org.opencontainers.image.source=https://github.com/openzim/zimwright

# Install necessary packages
RUN python -m pip install --no-cache-dir -U \
     pip

RUN mkdir -p /output
WORKDIR /output

# Copy pyproject.toml and its dependencies
COPY README.md /src/
COPY scraper/pyproject.toml /src/scraper/
COPY scraper/src/zimwright/__about__.py /src/scraper/src/zimwright/__about__.py

# Install Python dependencies
RUN pip install --no-cache-dir /src/scraper

# Copy code + associated artifacts
COPY scraper/src /src/scraper/src
COPY *.md LICENSE /src/

# Install + cleanup
RUN pip install --no-cache-dir /src/scraper \
 && rm -rf /src/scraper

ENV ZIMWRIGHT_OUTPUT=/output \
    ZIMWRIGHT_CONTACT_INFO=https://www.kiwix.org

CMD ["zimwright", "--help"]
