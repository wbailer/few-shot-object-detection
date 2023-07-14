# Few-Shot Object Detection (FsDet) Docker Container

## Building the container

Run ```build_image.sh``` to build the Docker container. It is by default labelled as ```fsdet_ms```.

Note: The build script assumes that it is called out of the ```docker``` directory of the code, and will access the configuration and model files from the respective directories of the fsdet installation.

## Running the container

An example command for running the container is

```
docker run --rm --gpus 0 -p:3000:3000 -p 3010:3010 -p 8080:8080 -p 8081:8081 --shm-size=1gb -v /home/myself/fsdet/few-shot-object-detection/datasets/coco:/workspace/few-shot-object-detection/datasets/coco fsdet_ms
```

where the volume contains the (mounted) dataset directories for the base dataset(s), e.g. COCO. ```shm-size``` is needed to adjust the shared memory size. The following ports are to be mapped:
- Torchserve (8080, 8081)
- Training service (3010)
- MakeSense annotation tool (3000)


## Training service 

The training service takes the configuration of a training job, the sample images and a COCO format annotation file as an input. It then runs the few shot training script and deploys the resulting model to the TorchServe instance in the container. The output is written to a log.

### Start training job

The training service is invoked as:

```
curl -F config=@../config.zip -F images=@../images.zip "http://localhost:3010/train"
```

The ZIP file passed to config contains the configuration of the training job:
- The dataset configuration file as described in the [script documentation](../README.md). Note that the ```name``` entry of the file will be used as the name of the training job.
- The JSON file with COCO format annotations.

The images ZIP file contains all the images referenced in the annotation file as a flat list.


### Access logs

The training script produces a log, with the name of the training job. The log can be accessed as (assuming the training job is called ```COCO60_myclasses```)

```
curl -v "http://localhost:3010/log?name=COCO60_myclasses"
```

To access just the last k (e.g., 10) lines of the log, use the ```tail``` parameter:

```
curl -v "http://localhost:3010/log?name=COCO60_myclasses&tail=10"
```


## Inference service

The inference service is implemented using TorchServe. Two models are deployed by default:
- fsod_base_coco80: The model trained on the 80 COCO classes.
- fsod_base_coco60: The model trained on the 60 COCO classes treated as base classes in [Frustratingly Simple Few-Shot Object Detection](https://arxiv.org/abs/2003.06957).

From the machine hosting the Docker container, inference can be invoked as:

```
curl http://localhost:8080/predictions/fsod_base_coco80 -T ~/my_sample_image.jpg 
```

Model created during the few-shot training process and deployed to TorchServe can be called in a similar way.

### Acknowledgement

This work has received funding from the European Union’s Horizon 2020 Research and Innovation Programme under grant agreement No 951911 ([AI4Media](https://www.ai4media.eu/)).
