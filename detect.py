import time
from pathlib import Path

from numpy import random
import cv2
import torch

from utils.datasets import LoadImages

from utils.general import (
    check_img_size,
    box_xyxy_to_cxcywh, plot_one_box,
    set_logging,
)

from hubconf import yolov5


def get_coco_names(category_path):
    names = []
    with open(category_path, 'r') as f:
        for line in f:
            names.append(line.strip())
    return names


@torch.no_grad()
def overlay_boxes(detections, path, img, time_consume, args):

    for i, pred in enumerate(detections):  # detections per image
        s = '%g: ' % i if args.webcam else ''
        save_path = Path(args.output_dir).joinpath(Path(path).name)
        txt_path = Path(args.output_dir).joinpath(Path(path).stem)
        s += '%gx%g ' % img.shape[:2]  # print string

        if pred is not None and len(pred) > 0:
            # Rescale boxes from img_size to im0 size
            boxes, scores, labels = pred['boxes'].round(), pred['scores'], pred['labels']

            # Print results
            for c in labels.unique():
                n = (labels == c).sum()  # detections per class
                s += '%g %ss, ' % (n, args.names[int(c)])  # add to string

            # Write results
            for xyxy, conf, cls_name in zip(boxes, scores, labels):
                if args.save_txt:  # Write to file
                    # normalized xywh
                    xywh = box_xyxy_to_cxcywh(xyxy).tolist()
                    with open(f'{txt_path}.txt', 'a') as f:
                        f.write(('%g ' * 5 + '\n') % (cls_name, *xywh))  # label format

                if args.save_img or args.view_img:  # Add bbox to image
                    label = '%s %.2f' % (args.names[int(cls_name)], conf)
                    plot_one_box(xyxy, img, label=label, color=args.colors[int(cls_name)], line_thickness=3)

        # Print inference time
        print('%sDone. (%.3fs)' % (s, time_consume))

        # Save results (image with detections)
        if args.save_img and args.mode == 'images':
            cv2.imwrite(str(save_path), img)

    return (boxes.tolist(), scores.tolist(), labels.tolist())


def main(args):
    print(args)

    device = torch.device(args.device)

    model = yolov5(cfg_path=args.model_cfg, checkpoint_path=args.model_checkpoint)
    model.eval()
    model = model.to(device)

    args.webcam = (args.image_source.isnumeric() or args.image_source.startswith(
        ('rtsp://', 'rtmp://', 'http://')) or args.image_source.endswith('.txt'))

    # Initialize
    set_logging()

    # half = device.type != 'cpu'  # half precision only supported on CUDA
    is_half = False

    # Load model
    imgsz = check_img_size(args.img_size, s=model.box_head.stride.max())  # check img_size
    if is_half:
        model.half()  # to FP16

    # Set Dataloader
    dataset = LoadImages(args.image_source, img_size=imgsz)
    args.mode = dataset.mode

    # Get names and colors
    args.names = get_coco_names(Path(args.coco_category_path))
    args.colors = [[random.randint(0, 255) for _ in range(3)] for _ in range(len(args.names))]

    # Run inference
    t0 = time.time()
    img = torch.zeros((1, 3, imgsz, imgsz), device=device)  # init img
    _ = model(img.half() if is_half else img) if device.type != 'cpu' else None  # run once

    for path, img, im0s, vid_cap in dataset:
        img = torch.from_numpy(img).to(device)
        model_out, time_consume = inference(model, img, is_half)

        # Process detections
        _ = overlay_boxes(model_out, path, img, im0s, time_consume, args)

    if args.save_txt or args.save_img:
        print(f'Results saved to {args.output_dir}')

    print('Done. (%.3fs)' % (time.time() - t0))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--model-cfg', type=str, default='./models/yolov5s.yaml',
                        help='path where the model cfg in')
    parser.add_argument('--model-checkpoint', type=str, default='./checkpoints/yolov5/yolov5s.pt',
                        help='path where the model checkpoint in')
    parser.add_argument('--coco-category-path', type=str, default='./libtorch_inference/weights/coco.names',
                        help='path where the coco category in')
    parser.add_argument('--image-source', type=str, default='./.github/',
                        help='path where the source images in')
    parser.add_argument('--output-dir', type=str, default='./data-bin/output',
                        help='path where to save')
    parser.add_argument('--img-size', type=int, default=640,
                        help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.4,
                        help='object confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.5,
                        help='IOU threshold for NMS')
    parser.add_argument('--device', default='cuda',
                        help='device')
    parser.add_argument('--view-img', action='store_true',
                        help='display results')
    parser.add_argument('--save-txt', action='store_true',
                        help='save results to *.txt')
    parser.add_argument('--save-img', action='store_true',
                        help='save image inference results')
    parser.add_argument('--classes', nargs='+', type=int,
                        help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true',
                        help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true',
                        help='augmented inference')

    args = parser.parse_args()

    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    main(args)