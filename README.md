# Self-Driving Perception Model in Simulation

This repository contains the implementation of the research paper [Towards Optimal Strategies for Training Self-Driving Perception Models in Simulation](https://research.nvidia.com/labs/toronto-ai/simulation-strategies/). The paper focused on the bird’s-eye-view vehicle segmentation task with multi-sensor data (cameras, lidar) using the open-source simulator CARLA, and evaluated the framework on the real-world dataset nuScenes. This implementation uses only the camera sensor for the task.

## File Structure

- **RAugment.py**: Data augmentation functions for training.
- **core.py**: Core functionalities for the self-driving perception model.
- **data.py**: Data handling and loading functions.
- **losses.py**: Custom loss functions for training.
- **model.py**: Definition of the model architecture.
- **tools.py**: Utility functions for the project.
- **train.py**: Script for training the self-driving perception model.
- **utils.py**: Additional utility functions for the project.
- **README.md**: This file.

## Getting Started

### Prerequisites

Ensure you have Python and the necessary packages installed. Consider creating a virtual environment for this project.

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/MacOS
# source venv/Scripts/Activate  # Windows

python train.py


```


## References

1. **Acuna, David, et al.** "f-Domain-Adversarial Learning: Theory and Algorithms." In *Proceedings of the 38th International Conference on Machine Learning*. [Link to Paper](https://proceedings.mlr.press/v139/acuna21a.html).

2. **Philion, Jonah, et al.** "Lift, Splat, Shoot: Encoding Images from Arbitrary Camera Rigs by Implicitly Unprojecting to 3D." *ECCV 2020*. [Link to Paper](https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123460143.pdf).

3. **Towards Optimal Strategies for Training Self-Driving Perception Models in Simulation**. [Link to Research Paper](https://research.nvidia.com/labs/toronto-ai/simulation-strategies/).
