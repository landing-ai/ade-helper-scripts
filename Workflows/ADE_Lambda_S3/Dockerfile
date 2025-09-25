FROM public.ecr.aws/lambda/python:3.12

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy Lambda handler
COPY handler.py /var/task
COPY config.py /var/task

# Set the handler
CMD ["handler.lambda_handler"]
