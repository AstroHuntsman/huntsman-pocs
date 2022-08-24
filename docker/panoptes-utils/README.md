Docker Images
=============

### Building a panoptes-utils image

To generate a new panoptes-utils docker image run the following from this directory.

```docker image build .
```

Once the image is built it can be tagged and pushed to the huntsmanarray dockerhub account.
Select a tag name that makes the most sense, ie if the image is for a specific release of 
panoptes-utils, use the release number as the tag e.g. v.0.2.35.


```docker tag <new-image-id> huntsmanarray/panoptes-utils:<tagname>
```

Once you have tagged the image you can then push it to docker hub

```docker push huntsmanarray/panoptes-utils:<tagname>
```
