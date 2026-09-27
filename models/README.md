# Model weights

Weights are not committed to git. Put them in this folder.

## Option A: use the original APTOS 2019 weights

1. Download `classifier.pt` from
   <https://www.kaggle.com/souravs17031999/blindness-detection-pretrained-weights-pytorch>.
2. This file was saved with the whole Python model pickled inside it, so it can't be
   loaded safely as it is. Convert it once:

   ```bash
   drscreen convert-weights ~/Downloads/classifier.pt models/classifier.pt --trust
   ```

   The converted file stores only tensors and metadata. The metadata includes the
   BGR channel order the original model was trained with.

## Option B: train your own

```bash
drscreen train --csv aptos/train.csv --images aptos/train_images --output models/classifier.pt
```

Check any checkpoint with `drscreen evaluate` before you use it on patients (see ../docs/MODEL_CARD.md).
