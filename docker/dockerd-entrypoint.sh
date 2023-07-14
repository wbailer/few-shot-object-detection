#!/bin/bash

echo entrypoint

cd /workspace/few-shot-object-detection
python3 fsserver.py &


torchserve --ncs --start --ts-config /home/model-server/config.properties --models fsod_base_coco60=fsod_base_coco60.mar fsod_base_coco80=fsod_base_coco80.mar #&

echo done

cd /workspace/make-sense
npm start 


