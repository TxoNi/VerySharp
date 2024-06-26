# -*- coding: utf-8 -*-
"""
    This file is part of verysharp,
    copyright (c) 2016 Björn Sonnenschein.

    verysharp is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    verysharp is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with verysharp.  If not, see <http://www.gnu.org/licenses/>.
"""

import cv2
import numpy as np
import CommonFunctions

class ImageAligner:
    
    ## The constructor
    #  @param reference_image the reference Image as float numpy array
    def __init__(self, scale_factor):
        self.scale_factor = scale_factor
        self.motion_type = cv2.MOTION_AFFINE

    def estimateRigidTransform (self,im1,im2):

        WIDTH=160
        HEIGHT=120
        COUNT=15

        sz0_height,sz0_width,cn=im1.shape;
        sz1_height=HEIGHT
        sz1_width=WIDTH

        scale = max(1.0, max( float(sz1_width)/float(sz0_width), float(sz1_height)/float(sz0_height) ));


        sz1_width=round(sz0_width*scale)
        sz1_height=round(sz0_height*scale)
        sz1=(sz1_height,sz1_width)

        if (cn!=1): #Convert 3 channels to grayscale
                im1_gray = cv2.cvtColor(im1, cv2.COLOR_BGR2GRAY)
                im1_gray = cv2.resize( im1_gray, sz1,0.0,0.0,interpolation = cv2.INTER_AREA )
                im2_gray = cv2.cvtColor(im2, cv2.COLOR_BGR2GRAY)
                im2_gray = cv2.resize( im2_gray, sz1,0.0,0.0,interpolation = cv2.INTER_AREA )

        else:
                im1_gray = im1
                im2_gray = im2


        count_y = COUNT
        count_x = round(float(COUNT)*float(sz1_width)/float(sz1_height));
        count = count_x * count_y;

        pA=np.empty((count,2),np.float32);
        pB=np.empty((count,2),np.float32);



        status=np.empty(count);

        k=0;

        for i in range(count_y): #0... < count_y
            for j in range(count_x): #0... < count_x
                pA[k]=[(j+0.5)*sz1_width/count_x,(i+0.5)*sz1_height/count_y] # [x, y];
                k=k+1


        # find the corresponding points in im2


        cv2.calcOpticalFlowPyrLK(im1_gray, im2_gray, pA, pB, status, None, [21, 21], 3,
                             (cv2.TERM_CRITERIA_MAX_ITER, 40, 0.1))

        [tmatrix,inliers]=cv2.estimateAffine2D(pA,pB)
        return (tmatrix)

    ## Calculate the Transformation matrices for all images in the dataset
    #  @param dataset ImageDataHolder object with filled hdulists and empty 
    #  transform matrices
    #  @return dataset with filled tansform_matrices for upscaled images
    def calculateTransformationMatrices(self, dataset, tiles, continue_processing, signal_status_update):
        # fill unity matrix for first image
        for tile in tiles:
            unity_transform_matrix = np.eye(2, 3, dtype=np.float32)
            dataset.appendTransformMatrix(0, unity_transform_matrix)  #@todo: is this possible inplace?
        
        # set the first image as reference
        first_data = dataset.getData(0)
        reference_image = CommonFunctions.preprocessImage(first_data["image"],
                                                          self.scale_factor,
                                                          data_type=np.uint8,
                                                          interpolation=cv2.INTER_CUBIC)
    
        # iterate through the dataset and create the tansformation matrix for each.
        # except the first one
        num_images = dataset.getImageCount()
        for index in range(1, num_images):
            
            if continue_processing[0] == False:
                return "aborted"
            
            print ("calculating transformation map for alignment of image ", index + 1)      
            
            # Get the image at the index
            data = dataset.getData(index)
            image = CommonFunctions.preprocessImage(data["image"],
                                                    self.scale_factor,
                                                    data_type=np.uint8,
                                                    interpolation=cv2.INTER_CUBIC)
            
            previous_transform_matrix = np.eye(2,3, dtype=np.float32)
            
            counter = 0
            for tile in tiles:
                
                if continue_processing[0] == False:
                    return "aborted"
                    
                percentage_finished = round(100. * float(counter) / float(len(tiles)))
                status = ("aligning image " 
                          + str(index + 1) 
                          + " of " 
                          + str(num_images)
                          + ": "
                          + str(percentage_finished)
                          + "%")
                signal_status_update.emit(status)
                counter += 1
                
                tile_slice = np.s_[tile["y"][0]:tile["y"][1],tile["x"][0]:tile["x"][1]]
#                print (tile_slice)
#                print(image.shape)
#                print(reference_image.shape)
                reference_tile = reference_image[tile_slice]
                image_tile = image[tile_slice]
            
                # convert image to 8u and greyscale for alignment functions
                image_tile_C1 = cv2.cvtColor(image_tile, cv2.COLOR_BGR2GRAY)
                reference_tile_C1 = cv2.cvtColor(reference_tile, cv2.COLOR_BGR2GRAY)
                
                # rough inital alignment using feature detection


                warp_matrix = self.estimateRigidTransform(reference_tile, image_tile)
                
                # if estimateRigidTransform has failed, create unity matrix
                if warp_matrix is None:
                    print ("WARNING: Initial alignment for Image ", index + 1, " failed!")
                    warp_matrix = np.eye(2,3, dtype=np.float32)
                
                # convert warp matrix to float32 because findTransformECC needs this

                warp_matrix = warp_matrix.astype(np.float32)   
                
                # @todo: those two parameters can be set in config!
                # Specify the number of iterations for ECC alignment.
                number_of_iterations = 500;
                 
                # Specify the threshold of the increment
                # in the correlation coefficient between two iterations
                termination_eps = 1e-5;
                
                # Define termination criteria
                criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                            number_of_iterations,  termination_eps)
                
                # Run the ECC algorithm. The results are stored in warp_matrix.
                try:
                    (cc, transform_matrix) = cv2.findTransformECC(reference_tile_C1,
                                                                  image_tile_C1, 
                                                                  warp_matrix, 
                                                                  self.motion_type, 
                                                                  criteria)
                except:
                    transform_matrix = previous_transform_matrix
            
                # fill the warp matrix into the dataset
                dataset.appendTransformMatrix(index, transform_matrix)
                
                # if next tile fails, use this one instead
                previous_transform_matrix = transform_matrix
            
        return dataset
