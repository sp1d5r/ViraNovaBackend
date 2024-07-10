

def smooth_bounding_boxes(bboxes, window_size=3):
    smoothed_boxes = []
    for i in range(len(bboxes)):
        x1, y1, x2, y2 = 0, 0, 0, 0
        count = 0
        for j in range(max(0, i - window_size//2), min(len(bboxes), i + window_size//2 + 1)):
            x1 += bboxes[j][0]
            y1 += bboxes[j][1]
            x2 += bboxes[j][2]
            y2 += bboxes[j][3]
            count += 1
        smoothed_boxes.append([x1 // count, y1 // count, x2 // count, y2 // count])
    return smoothed_boxes

def exponential_smoothing(bboxes, alpha=0.3):
    smoothed_boxes = [bboxes[0]]
    for i in range(1, len(bboxes)):
        prev_box = smoothed_boxes[-1]
        curr_box = bboxes[i]
        new_box = [
            alpha * curr_box[0] + (1 - alpha) * prev_box[0],
            alpha * curr_box[1] + (1 - alpha) * prev_box[1],
            alpha * curr_box[2] + (1 - alpha) * prev_box[2],
            alpha * curr_box[3] + (1 - alpha) * prev_box[3],
        ]
        smoothed_boxes.append([int(x) for x in new_box])
    return smoothed_boxes