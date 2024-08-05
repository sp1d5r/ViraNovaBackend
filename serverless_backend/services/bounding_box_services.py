def smooth_bounding_boxes(bboxes, window_size=3):
    if not bboxes:
        return []

    if isinstance(bboxes[0], tuple) and len(bboxes[0]) == 2:  # two_boxes type
        return smooth_two_boxes(bboxes, window_size)
    else:  # single box type
        return smooth_single_box(bboxes, window_size)


def smooth_single_box(bboxes, window_size=3):
    smoothed_boxes = []
    for i in range(len(bboxes)):
        if bboxes[i] is None:
            smoothed_boxes.append(None)
            continue

        x, y, w, h = 0, 0, 0, 0
        count = 0
        for j in range(max(0, i - window_size // 2), min(len(bboxes), i + window_size // 2 + 1)):
            if bboxes[j] is not None:
                x += bboxes[j][0]
                y += bboxes[j][1]
                w += bboxes[j][2]
                h += bboxes[j][3]
                count += 1
        if count > 0:
            smoothed_boxes.append((x // count, y // count, w // count, h // count))
        else:
            smoothed_boxes.append(None)
    return smoothed_boxes


def smooth_two_boxes(bboxes, window_size=3):
    smoothed_boxes = []
    for i in range(len(bboxes)):
        if bboxes[i] is None:
            smoothed_boxes.append(None)
            continue

        box1, box2 = bboxes[i]
        smoothed_box1 = [0, 0, 0, 0]
        smoothed_box2 = [0, 0, 0, 0]
        count = 0
        for j in range(max(0, i - window_size // 2), min(len(bboxes), i + window_size // 2 + 1)):
            if bboxes[j] is not None:
                b1, b2 = bboxes[j]
                for k in range(4):
                    smoothed_box1[k] += b1[k]
                    smoothed_box2[k] += b2[k]
                count += 1
        if count > 0:
            smoothed_boxes.append((
                tuple(x // count for x in smoothed_box1),
                tuple(x // count for x in smoothed_box2)
            ))
        else:
            smoothed_boxes.append(None)
    return smoothed_boxes