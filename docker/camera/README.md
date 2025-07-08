Docker Images
=============

### Building a camera image

To generate a new camera docker image run the following from this directory.

```docker image build .
```

Once the image is built it can be tagged and pushed to the huntsmanarray dockerhub account.


```docker tag <new-image-id> huntsmanarray/huntsman-pocs-camera:<tagname>
```

Once you have tagged the image you can then push it to docker hub

```docker push huntsmanarray/huntsman-pocs-camera:<tagname>
```

For creating image for both x86_64 and arm64 architectures, you need to run the following command:

```docker buildx build --platform linux/amd64,linux/arm64 -t huntsmanarray/huntsman-pocs-camera:develop --push .```
