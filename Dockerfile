# Dockerfile for the Pangea/BNP scraping robot
#
# This image installs a minimal Python runtime together with
# Chromium and the ChromeDriver required by selenium.  It then
# installs the Python dependencies and copies the scraper script into
# ``/usr/src/app``.  The default entrypoint runs the script and
# writes the Excel file into the container's working directory.

FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    # Install Chromium and related dependencies.  The libgconf-2-4
    # package is not available on newer Debian releases, so it has been
    # removed.  The webdriver-manager Python package will download
    # the appropriate chromedriver at runtime, so the separate
    # chromium-driver package is optional and therefore omitted here.
    apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-liberation \
        libnss3 \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir selenium webdriver-manager pandas openpyxl

# Set up application directory
WORKDIR /usr/src/app
COPY pangea_scrape.py ./

# By default run the scraper.  The output file can be overridden via
# the command line when running the container (e.g. docker run ... --output /data/out.xlsx)
ENTRYPOINT ["python", "pangea_scrape.py"]