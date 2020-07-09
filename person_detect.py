
import numpy as np
import time
from openvino.inference_engine import IENetwork, IECore
import os
import cv2
import argparse
import sys


class Queue:
    '''
    Class for dealing with queues
    '''
    def __init__(self):
        self.queues=[]

    def add_queue(self, points):
        self.queues.append(points)

    def get_queues(self, image):
        for q in self.queues:
            x_min, y_min, x_max, y_max=q
            frame=image[y_min:y_max, x_min:x_max]
            yield frame
    
    def check_coords(self, coords):
        d={k+1:0 for k in range(len(self.queues))}
        for coord in coords:
            for i, q in enumerate(self.queues):
                if coord[0]>q[0] and coord[2]<q[2]:
                    d[i+1]+=1
        return d


class PersonDetect:
    '''
    Class for the Person Detection Model.
    '''

    def __init__(self, model_name, device, threshold=0.60):
        self.model_weights=model_name+'.bin'
        self.model_structure=model_name+'.xml'
        self.device=device
        self.threshold=threshold
        self.exec_net = None
        self.image = None

        try:
            self.model=IENetwork(self.model_structure, self.model_weights)
        except Exception as e:
            raise ValueError("Could not Initialise the network. Have you enterred the correct model path?")

        self.input_name=next(iter(self.model.inputs))
        self.input_shape=self.model.inputs[self.input_name].shape
        self.output_name=next(iter(self.model.outputs))
        self.output_shape=self.model.outputs[self.output_name].shape

    def load_model(self):
        '''
        Description: Function to load model to IECore and get executable network
        '''
        core = IECore()
        self.exec_net = core.load_network(network = self.model, device_name = self.device) 
        
    def predict(self, image):
        '''
        Description: Function to run inference on image
        Params:
            image: Input Image
        Returns:
            coords:
            self.image: 
        '''
        self.image = image
        processed_image = self.preprocess_input(image)
        input_dict = {self.input_name: processed_image}
        outputs = self.exec_net.infer(input_dict)
        coords = self.preprocess_outputs(outputs)

        return coords, self.image
    
    def draw_outputs(self, coords):
        '''
        Description: Drawing Boxes to the detection output according to box coordinates
        params:
            coords: Detected Person Coordinates
        returns:
            xmin, xmax: X-Axis Length of Box
            ymin, ymax: Y-Axis Lenght of Box
        '''
        xmin = int(coords[0] * self.image.shape[1])
        ymin = int(coords[1] * self.image.shape[0])
        xmax = int(coords[2] * self.image.shape[1])
        ymax = int(coords[3] * self.image.shape[0])
        cv2.rectangle(self.image, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)

        return xmin, ymin, xmax, ymax

    def preprocess_outputs(self, outputs):
        '''
        Description: Takes in the outputs of the model and then transforms them to the image
        params:
            outputs: Model Outputs
        returns:
            coords: Here, array of detected objects with their coordinates.
        '''
        boxes = outputs[self.output_name]
        coords = []
        for box in boxes[0][0]:
            if box[2] > self.threshold:
                xmin, ymin, xmax, ymax = self.draw_outputs((box[3], box[4], box[5], box[6]))
                coords.append((xmin, ymin, xmax, ymax))

        return coords

    def preprocess_input(self, image):
        '''
        Description: Preprocesses the Input image accordin to model size
        params:
            image: Input Image
        returns:
            processed_image: Image that can now be used with the model
        '''
        processed_image = cv2.resize(image, (self.input_shape[3], self.input_shape[2]))
        processed_image = processed_image.transpose((2,0,1))
        processed_image = processed_image.reshape(1, *processed_image.shape)
        
        return processed_image
        

def main(args):
    model=args.model
    device=args.device
    video_file=args.video
    max_people=args.max_people
    threshold=args.threshold
    output_path=args.output_path

    start_model_load_time=time.time()
    pd= PersonDetect(model, device, threshold)
    pd.load_model()
    total_model_load_time = time.time() - start_model_load_time

    queue=Queue()
    
    try:
        queue_param=np.load(args.queue_param)
        for q in queue_param:
            queue.add_queue(q)
    except:
        print("error loading queue param file")

    try:
        cap=cv2.VideoCapture(video_file)
    except FileNotFoundError:
        print("Cannot locate video file: "+ video_file)
    except Exception as e:
        print("Something else went wrong with the video file: ", e)
    
    initial_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    initial_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_len = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    out_video = cv2.VideoWriter(os.path.join(output_path, 'output_video.mp4'), cv2.VideoWriter_fourcc(*'avc1'), fps, (initial_w, initial_h), True)
    
    counter=0
    start_inference_time=time.time()

    try:
        while cap.isOpened():
            ret, frame=cap.read()
            if not ret:
                break
            counter+=1
            
            coords, image= pd.predict(frame)
            num_people= queue.check_coords(coords)
            print(f"Total People in frame = {len(coords)}")
            print(f"Number of people in queue = {num_people}")
            out_text=""
            y_pixel=25
            
            for k, v in num_people.items():
                out_text += f"No. of People in Queue {k} is {v} "
                if v >= int(max_people):
                    out_text += f" Queue full; Please move to next Queue "
                cv2.putText(image, out_text, (15, y_pixel), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 255, 0), 2)
                out_text=""
                y_pixel+=40
            out_video.write(image)
            
        total_time=time.time()-start_inference_time
        total_inference_time=round(total_time, 1)
        fps=counter/total_inference_time

        with open(os.path.join(output_path, 'stats.txt'), 'w') as f:
            f.write(str(total_inference_time)+'\n')
            f.write(str(fps)+'\n')
            f.write(str(total_model_load_time)+'\n')

        cap.release()
        cv2.destroyAllWindows()
    except Exception as e:
        print("Could not run Inference: ", e)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--device', default='CPU')
    parser.add_argument('--video', default=None)
    parser.add_argument('--queue_param', default=None)
    parser.add_argument('--output_path', default='/results')
    parser.add_argument('--max_people', default=2)
    parser.add_argument('--threshold', default=0.60)
    
    args=parser.parse_args()

    main(args)