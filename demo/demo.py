import cv2
import tqdm

import argparse
import glob
import multiprocessing as mp
import os
import time
import json
import sys
import numpy as np

from demo.predictor import VisualizationDemo
from detectron2.data.detection_utils import read_image
from detectron2.utils.logger import setup_logger
from fsdet.config import get_cfg
from fsdet.data import custom_dataset

# constants
WINDOW_NAME = "COCO detections"


def setup_cfg(args):
    # load config from file and command-line arguments
    cfg = get_cfg()
    cfg.merge_from_file(args.config_file)
    cfg.merge_from_list(args.opts)
    # Set score_threshold for builtin models
    cfg.MODEL.RETINANET.SCORE_THRESH_TEST = args.confidence_threshold
    cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = args.confidence_threshold
    cfg.freeze()
    return cfg


def get_parser():
    parser = argparse.ArgumentParser(
        description="FsDet demo for builtin models"
    )
    parser.add_argument(
        "--config-file",
        default="configs/COCO-detection/faster_rcnn_R_101_FPN_ft_all_1shot.yaml",
        metavar="FILE",
        help="path to config file",
    )
    parser.add_argument(
        "--webcam", action="store_true", help="Take inputs from webcam."
    )
    parser.add_argument("--video-input", help="Path to video file.")
    parser.add_argument(
        "--input",
        nargs="+",
        help="A list of space separated input images; "
        "or a single glob pattern such as 'directory/*.jpg'",
    )
    parser.add_argument(
        "--output",
        help="A file or directory to save output visualizations. "
        "If not given, will show output in an OpenCV window.",
    )
    parser.add_argument(
        "--json",
        help="JSON output file. "
    )    
    

    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.1,
        help="Minimum score for instance predictions to be shown",
    )
    parser.add_argument(
        "--custom-dataset",
        type=str,
        help="Custom dataset configuration file",
    )
    parser.add_argument(
        "--opts",
        help="Modify config options using the command-line 'KEY VALUE' pairs",
        default=[],
        nargs=argparse.REMAINDER,
    )
    return parser


def main(myargs):
    sys.argv = ["demo.py"]+myargs

    mp.set_start_method("spawn", force=True)
    args = get_parser().parse_args()
    setup_logger(name="fvcore")
    logger = setup_logger()
    logger.info("Arguments: " + str(args))


    if not (args.custom_dataset == None):
    
        custom_dataset.register_all_custom(args.custom_dataset,"datasets")


    cfg = setup_cfg(args)

    demo = VisualizationDemo(cfg)

    if args.input:
        if len(args.input) == 1:
            args.input = glob.glob(os.path.expanduser(args.input[0]))
            assert args.input, "The input path(s) was not found"
        for path in tqdm.tqdm(args.input, disable=not args.output):
            # use PIL, to be consistent with evaluation
            img = read_image(path, format="BGR")
            start_time = time.time()
            predictions, visualized_output = demo.run_on_image(img)
                        
            logger.info(
                "{}: {} in {:.2f}s".format(
                    path,
                    "detected {} instances".format(
                        len(predictions["instances"])
                    )
                    if "instances" in predictions
                    else "finished",
                    time.time() - start_time,
                )
            )

            if args.output:
                if os.path.isdir(args.output):
                    assert os.path.isdir(args.output), args.output
                    out_filename = os.path.join(
                        args.output, os.path.basename(path)
                    )
                else:
                    assert (
                        len(args.input) == 1
                    ), "Please specify a directory with args.output"
                    out_filename = args.output
                visualized_output.save(out_filename)
            else:
                cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
                cv2.imshow(
                    WINDOW_NAME, visualized_output.get_image()[:, :, ::-1]
                )
                if cv2.waitKey(0) == 27:
                    break  # esc to quit
                    
            if args.json:
                annot = {}
                annot["annotations"] = []
                   
                pred = predictions["instances"]
                   
                for i in range(len(pred)):
                
                    annoI = {}
                    annoI["id"] = time.time()
                    annoI["image_id"] = -1
                    annoI["iscrowd"] = 0
                    annoI["bbox"] = list(np.array(pred.get('pred_boxes').tensor[i].cpu()).astype(np.float))
                    annoI["category_id"] = pred.get('pred_classes')[i].item()+1
                    annoI["score"] = pred.get('scores')[i].item()
                    
                
 #               'instances': Instances(num_instances=1, image_height=427, image_width=640, fields=[pred_boxes: Boxes(tensor([[168.7178, 132.6446, 418.1703, 315.9247]], device='cuda:0')), scores: tensor([0.2292], device='cuda:0'), pred_classes: tensor([21], device='cuda:0')])}
               
                    annot["annotations"].append(annoI)
                   

                
                with open(args.json,'w') as outfile:
                    json.dump(annot,outfile)
                    
 #                   "annotations": [{"segmentation": [[90.0, 205.46, 169.46, 198.76, 193.39, 190.14, 146.48, 170.99, 172.33, 166.2, 248.92, 180.57, 299.67, 171.95, 372.43, 184.4, 361.9, 201.63, 332.22, 204.5, 332.22, 208.33, 431.79, 235.14, 508.38, 227.48, 539.02, 193.01, 561.04, 183.44, 588.8, 193.97, 610.82, 235.14, 605.08, 262.9, 599.33, 282.05, 580.18, 292.58, 569.65, 294.5, 580.18, 302.16, 591.67, 309.81, 582.1, 320.35, 568.7, 315.56, 561.99, 303.11, 554.33, 297.37, 305.41, 280.13, 204.88, 267.69, 204.88, 294.5, 220.2, 304.07, 215.41, 316.52, 202.01, 319.39, 166.59, 322.26, 157.01, 314.6, 157.01, 303.11, 169.46, 296.41, 184.78, 272.48, 131.16, 264.82, 104.36, 235.14, 97.65, 224.61, 81.38, 212.16]], "area": 43807.8147, "iscrowd": 0, "image_id": 377672, "bbox": [81.38, 166.2, 529.44, 156.06], "category_id": 5, "id": 159123}],
                    
    elif args.webcam:
        assert args.input is None, "Cannot have both --input and --webcam!"
        cam = cv2.VideoCapture(0)
        for vis in tqdm.tqdm(demo.run_on_video(cam)):
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            cv2.imshow(WINDOW_NAME, vis)
            if cv2.waitKey(1) == 27:
                break  # esc to quit
        cv2.destroyAllWindows()
    elif args.video_input:
        video = cv2.VideoCapture(args.video_input)
        width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames_per_second = video.get(cv2.CAP_PROP_FPS)
        num_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        basename = os.path.basename(args.video_input)

        if args.output:
            if os.path.isdir(args.output):
                output_fname = os.path.join(args.output, basename)
                output_fname = os.path.splitext(output_fname)[0] + ".mkv"
            else:
                output_fname = args.output
            assert not os.path.isfile(output_fname), output_fname
            output_file = cv2.VideoWriter(
                filename=output_fname,
                # some installation of opencv may not support x264 (due to its license),
                # you can try other format (e.g. MPEG)
                fourcc=cv2.VideoWriter_fourcc(*"x264"),
                fps=float(frames_per_second),
                frameSize=(width, height),
                isColor=True,
            )
        assert os.path.isfile(args.video_input)
        for vis_frame in tqdm.tqdm(demo.run_on_video(video), total=num_frames):
            if args.output:
                output_file.write(vis_frame)
            else:
                cv2.namedWindow(basename, cv2.WINDOW_NORMAL)
                cv2.imshow(basename, vis_frame)
                if cv2.waitKey(1) == 27:
                    break  # esc to quit
        video.release()
        if args.output:
            output_file.release()
        else:
            cv2.destroyAllWindows()
            
            
if __name__ == "__main__":
    main(sys.argv[1:])
    
