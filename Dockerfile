# --- Builder Stage (Optional, if you have Go application code) ---
# This stage is for building Go applications. If you don't have Go code
# that needs building, you can remove this entire stage.
FROM golang:1.16.2-alpine3.13 as builder
WORKDIR /app
COPY . ./
# Uncomment and modify the line below if you have a Go application to build
# RUN go build -o myapp .


# --- Main Application Stage ---
# This is the primary stage where all your tools and the Python application reside.
FROM alpine:latest

# Install core system dependencies using apk
# This ensures Python, Java, curl, git, build tools, etc., are available.
RUN apk update && \
    apk add --no-cache \
    ca-certificates \
    openssh \
    sudo \
    python3 \
    py3-pip \
    openjdk17-jre-headless \
    unzip \
    curl \
    git \
    bash \
    build-base \
    linux-headers \
    libffi-dev \
    openssl-dev \
    meson \
    ninja \
    vala \
    pkgconf \
    glib-dev \
    libusb-dev \
    nodejs \
    npm \
    bc \
    procps \
    wget && \
    rm -rf /var/cache/apk/*

# Define Android SDK Root directory
ENV ANDROID_SDK_ROOT="/opt/android-sdk"

# Install Android SDK Command-line Tools (includes sdkmanager)
# sdkmanager is essential for installing other SDK components.
RUN mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools/latest && \
    wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O /tmp/commandlinetools.zip && \
    unzip -q /tmp/commandlinetools.zip -d /tmp/sdk-temp && \
    mv /tmp/sdk-temp/cmdline-tools/* ${ANDROID_SDK_ROOT}/cmdline-tools/latest/ && \
    rm /tmp/commandlinetools.zip && \
    rm -rf /tmp/sdk-temp

# Set the Android Build Tools version
ENV ANDROID_BUILD_TOOLS_VERSION="34.0.0"

# Set the PATH correctly for SDK tools, including platform-tools, cmdline-tools, and build-tools.
# This makes commands like 'adb', 'sdkmanager', 'aapt', and 'apksigner' directly available.
ENV PATH="${PATH}:${ANDROID_SDK_ROOT}/platform-tools:${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin:${ANDROID_SDK_ROOT}/build-tools/${ANDROID_BUILD_TOOLS_VERSION}"

# Accept Android SDK licenses to allow SDK component installation
RUN yes | sdkmanager --licenses

# Install Android SDK Platform-Tools (includes adb, fastboot)
RUN sdkmanager "platform-tools"

# Install Android SDK Build-Tools (this includes apksigner, aapt, zipalign)
RUN sdkmanager "build-tools;${ANDROID_BUILD_TOOLS_VERSION}"

# Install Objection (Python package for mobile security)
RUN pip3 install --no-cache-dir objection --break-system-packages

# Install Apktool and create its wrapper script
ENV APKTOOL_VERSION=2.9.3
RUN wget https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_${APKTOOL_VERSION}.jar -O /usr/local/bin/apktool.jar && \
    printf '#!/usr/bin/env sh\njava -jar /usr/local/bin/apktool.jar "$@"\n' > /usr/local/bin/apktool && \
    chmod +x /usr/local/bin/apktool

# Install Smali/Baksmali and create their wrapper scripts
ENV SMALI_VERSION="2.5.2"
RUN wget https://bitbucket.org/JesusFreke/smali/downloads/smali-${SMALI_VERSION}.jar -O /usr/local/bin/smali.jar && \
    wget https://bitbucket.org/JesusFreke/smali/downloads/baksmali-${SMALI_VERSION}.jar -O /usr/local/bin/baksmali.jar && \
    printf '#!/usr/bin/env sh\njava -jar /usr/local/bin/smali.jar "$@"\n' > /usr/local/bin/smali && \
    printf '#!/usr/bin/env sh\njava -jar /usr/local/bin/baksmali.jar "$@"\n' > /usr/local/bin/baksmali && \
    chmod +x /usr/local/bin/smali /usr/local/bin/baksmali

# Install Dex2jar
ENV DEX2JAR_VERSION="2.4"
RUN wget https://github.com/pxb1988/dex2jar/releases/download/v${DEX2JAR_VERSION}/dex-tools-v${DEX2JAR_VERSION}.zip -O /tmp/dex2jar.zip && \
    unzip /tmp/dex2jar.zip -d /opt/dex2jar-unzipped && \
    mv /opt/dex2jar-unzipped/dex-tools-v${DEX2JAR_VERSION} /opt/dex2jar && \
    rm -rf /tmp/dex2jar.zip /opt/dex2jar-unzipped && \
    chmod +x /opt/dex2jar/*.sh && \
    ln -s /opt/dex2jar/*.sh /usr/local/bin/

# Install Jadx
ENV JADX_VERSION="1.5.2"
RUN wget https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip -O /tmp/jadx.zip && \
    unzip /tmp/jadx.zip -d /opt/jadx && \
    rm /tmp/jadx.zip && \
    chmod +x /opt/jadx/bin/jadx && \
    ln -s /opt/jadx/bin/jadx /usr/local/bin/jadx

# Install Python dependencies for your Vps.py script
# 'requests' is added here for file downloading capabilities.
RUN pip3 install --no-cache-dir python-telegram-bot requests --break-system-packages

# Install Frida tools (Python package)
RUN pip3 install --no-cache-dir frida-tools --break-system-packages

# Install frida-gadget (Pypi package for patching)
RUN pip3 install --no-cache-dir frida-gadget --break-system-packages

# Set working directory for the application
WORKDIR /app

# Copy Vps.py into the image
# Ensure Vps.py is in the same directory as your Dockerfile when building.
COPY Vps.py /app/Vps.py

# Define the command to run when the container starts.
# This will execute your Python Telegram bot script.
CMD ["python3", "/app/Vps.py"]
