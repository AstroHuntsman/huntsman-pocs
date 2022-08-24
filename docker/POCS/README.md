Docker Images
=============

### Building a panoptes-pocs image

To generate a new panoptes-pocs docker image run the following from this directory.

```docker image build .
```

NB: Huntsman-pocs test suite requires some files that are contained in panoptes-pocs. To ensure
These files are available in the directory the huntsman-pocs test suite expects them, make
sure the `tests/data/*` and `conf_files` directories from panoptes-pocs are present in this
folder. They will be copied into the docker image in the correct spot for the tests to access them.

Once the image is built it can be tagged and pushed to the huntsmanarray dockerhub account.
Select a tag name that makes the most sense, ie if the image is for a specific release of 
panoptes-utils, use the release number as the tag e.g. v.0.7.8.


```docker tag <new-image-id> huntsmanarray/panoptes-pocs:<tagname>
```

Once you have tagged the image you can then push it to docker hub

```docker push huntsmanarray/panoptes-pocs:<tagname>