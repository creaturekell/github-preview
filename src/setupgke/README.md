# Installation and step of Google Cloud Kubernetes Cluster

## Dependencies

 - [Google Cloud project](https://cloud.google.com/resource-manager/docs/creating-managing-projects#creating_a_project).
- Shell environment with `gcloud`, `git`, and `kubectl`.

## Cluster Set Up

1. Set the Google Cloud project and region and ensure the Google Kubernetes Engine API is enabled.

   ```bash
   export PROJECT_ID=<PROJECT_ID>
   export REGION=us-central1
   gcloud services enable container.googleapis.com \
     --project=${PROJECT_ID}
   ```

2. 

To destroy the cluster run:


