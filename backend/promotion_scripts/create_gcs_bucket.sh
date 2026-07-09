#!/bin/bash

# Script to create GCS bucket for spreadsheet conversions file uploads
# Bucket structure: upload/<submission_id>/<files>

if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Error: Missing required arguments."
  echo "Usage: $0 <project_id> <bucket_name>"
  echo "Example: $0 zen-general-377713 blonter_be"
  exit 1
fi

PROJECT_ID="$1"
BUCKET_NAME="$2"
LOCATION="us-east4"  # Default location, change as needed

echo "Creating GCS bucket: gs://${BUCKET_NAME}"
echo "Project: ${PROJECT_ID}"
echo "Location: ${LOCATION}"
echo ""

# Create the bucket
gcloud storage buckets create "gs://${BUCKET_NAME}" \
  --project="${PROJECT_ID}" \
  --location="${LOCATION}" \
  --uniform-bucket-level-access

if [ $? -eq 0 ]; then
  echo ""
  echo "✓ Bucket created successfully!"
  echo ""
  echo "Bucket details:"
  gcloud storage buckets describe "gs://${BUCKET_NAME}"
  echo ""
  echo "Files will be stored in structure: upload/<submission_id>/<filename>"
else
  echo ""
  echo "✗ Failed to create bucket"
  echo "The bucket may already exist or there may be a permissions issue"
  exit 1
fi
