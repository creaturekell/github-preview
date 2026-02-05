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
   Substitute `<PROJECT_ID>` with the ID of your Google Cloud project.

2. Create a GKE cluster and get the credentials for it. 

    ```bash
    gcloud container clusters create-auto preview-url-demo \
    --project-${PROJECT_ID}  --region=${REGION}
    ```

    Creating the cluster may take a few minutes

3. Deploy application to the cluster

    To testing out that the application deployment works.  This will eventually be executed by the deployer that would be called when a /preview is put in a PR comment and the GitHubApp queues up the deployment.


   ```bash
   kubectl apply -f ./release/placeholder-kub-manifests.yaml
   ``` 

4. Wait for pods to be ready

  ```bash
  kubectl get pods
  ```

  After a few minutes, you would see:

4. Access the frontend in a browser using the the frontend's external IP.

 ```bash
 kubectl get service preview-ip | awk '{print $4"}'
 ```

5. Congrats!

6. Once you are done with it, delete the GKE cluster.

   ```bash
   gcloud container clusters delete preview-url-demo \
     --project=${PROJECT_ID} --region=${REGION}
   ```

   Deleting the cluster may take a few minutes.

7. Looking to augment this demo by adding additional service, here are the instructions...


