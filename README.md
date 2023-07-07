# fDAL-Segmentation

# An implementation of [Toward Optimal Strategies for Training Self-Driving perception Models in Simulation](https://arxiv.org/abs/2111.07971) paper

what has been changed from Narendra's last work?

I made some modifications. 
1. As Narendra suggested I reduced the number of classes from 2 to 1 and solved the issues. 
2. I changed the model's architecture to be more similar to the original fDAL implementation 
3. I changed the loss function to include fdal loss but still have problems with pseudo loss

What are the current issues:
1. no sampling strategies to collect the dataset as the paper suggested
2. no style transfer as the paper suggested 
3. pseudo loss makes some problems

