FROM python:3.13-slim

WORKDIR /app

# System deps: LaTeX (for formula rendering), fonts, ffmpeg (for audio), and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    dvipng \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libfreetype6 \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps — split into layers so code changes don't re-install everything
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Additional packages not in requirements.txt
RUN pip install --no-cache-dir \
    matplotlib \
    PyMuPDF \
    python-docx \
    python-pptx \
    openpyxl \
    pydub

# Copy source code (data/ is volume-mounted, this brings in core/ and *.py)
COPY . .

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
