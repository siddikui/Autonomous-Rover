import numpy as np
import cv2

# Identify pixels above the threshold
# Threshold of RGB > 160 does a nice job of identifying ground pixels only
def color_thresh(img, rgb_thresh=(160, 160, 160)):
    # Create an empty array the same size in x and y as the image     
    combined = np.zeros_like(img)
    
    terrain = np.zeros_like(img[:,:,0])
    obstacles = np.zeros_like(img[:,:,0])
    rocks = np.zeros_like(img[:,:,0])
    
    thresh = (img[:,:,0]>rgb_thresh[0]) & (img[:,:,1]>rgb_thresh[1]) & (img[:,:,2]>rgb_thresh[2])
    terrain[thresh] = 255
  
    # THresholds do a reasonably good job for rock detection.
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    lower = np.array([20,100,100])
    upper = np.array([30,255,255])
    mask = cv2.inRange(hsv, lower, upper)
    res = cv2.bitwise_and(img,img, mask= mask)
    Gray = cv2.cvtColor(res, cv2.COLOR_RGB2GRAY)
    _,rocks = cv2.threshold(Gray,0,255,cv2.THRESH_BINARY)

    #Dilating rock samples since they are smaller
    #Should ideally help navigating towards rocks
    kernel = np.ones((7,7),np.uint8)
    rocks = cv2.dilate(rocks,kernel,iterations = 1)         

    thresh = (img[:,:,0]<rgb_thresh[0]) & (img[:,:,1]<rgb_thresh[1]) & (img[:,:,2]<rgb_thresh[2])
    obstacles[thresh] = 255    
    
    thresh = (rocks[:,:] == 255)
    obstacles[thresh] = 0
    #obstacles = obstacles - rocks
    
    combined = cv2.merge((obstacles,rocks,terrain))    

    return combined

# Define a function to convert from image coords to rover coords
def rover_coords(binary_img):
    # Identify nonzero pixels
    ypos, xpos = binary_img.nonzero()
    # Calculate pixel positions with reference to the rover position being at the 
    # center bottom of the image.  
    x_pixel = -(ypos - binary_img.shape[0]).astype(np.float)
    y_pixel = -(xpos - binary_img.shape[1]/2 ).astype(np.float)
    return x_pixel, y_pixel


# Define a function to convert to radial coords in rover space
def to_polar_coords(x_pixel, y_pixel):
    # Convert (x_pixel, y_pixel) to (distance, angle) 
    # in polar coordinates in rover space
    # Calculate distance to each pixel
    dist = np.sqrt(x_pixel**2 + y_pixel**2)
    # Calculate angle away from vertical for each pixel
    angles = np.arctan2(y_pixel, x_pixel)
    return dist, angles

# Define a function to map rover space pixels to world space
def rotate_pix(xpix, ypix, yaw):
    # Convert yaw to radians
    yaw_rad = yaw * np.pi / 180
    xpix_rotated = (xpix * np.cos(yaw_rad)) - (ypix * np.sin(yaw_rad))
                            
    ypix_rotated = (xpix * np.sin(yaw_rad)) + (ypix * np.cos(yaw_rad))
    # Return the result  
    return xpix_rotated, ypix_rotated

def translate_pix(xpix_rot, ypix_rot, xpos, ypos, scale): 
    # Apply a scaling and a translation
    xpix_translated = (xpix_rot / scale) + xpos
    ypix_translated = (ypix_rot / scale) + ypos
    # Return the result  
    return xpix_translated, ypix_translated


# Define a function to apply rotation and translation (and clipping)
# Once you define the two functions above this function should work
def pix_to_world(xpix, ypix, xpos, ypos, yaw, world_size, scale):
    # Apply rotation
    xpix_rot, ypix_rot = rotate_pix(xpix, ypix, yaw)
    # Apply translation
    xpix_tran, ypix_tran = translate_pix(xpix_rot, ypix_rot, xpos, ypos, scale)
    # Perform rotation, translation and clipping all at once
    x_pix_world = np.clip(np.int_(xpix_tran), 0, world_size - 1)
    y_pix_world = np.clip(np.int_(ypix_tran), 0, world_size - 1)
    # Return the result
    return x_pix_world, y_pix_world

# Define a function to perform a perspective transform
def perspect_transform(img, src, dst):
           
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (img.shape[1], img.shape[0]))# keep same size as input image
    mask = cv2.warpPerspective(np.ones_like(img[:,:,0]), M, (img.shape[1], img.shape[0]))
    return warped, mask


# Apply the above functions in succession and update the Rover state accordingly
def perception_step(Rover):
    # Perform perception steps to update Rover()
     
    # NOTE: camera image is coming to you in Rover.img
    img = Rover.img
    image = img
    # 1) Define source and destination points for perspective transform
    dst_size = 5 
    # Set a bottom offset to account for the fact that the bottom of the image 
    # is not the position of the rover but a bit in front of it
    # this is just a rough guess, feel free to change it!
    bottom_offset = 6
    source = np.float32([[14, 140], [301 ,140],[200, 96], [118, 96]])
    destination = np.float32([[image.shape[1]/2 - dst_size, image.shape[0] - bottom_offset],
                  [image.shape[1]/2 + dst_size, image.shape[0] - bottom_offset],
                  [image.shape[1]/2 + dst_size, image.shape[0] - 2*dst_size - bottom_offset], 
                  [image.shape[1]/2 - dst_size, image.shape[0] - 2*dst_size - bottom_offset],
                  ])

    # 2) Apply perspective transform
    warped, mask = perspect_transform(img, source, destination)

    # 3) Apply color threshold to identify navigable terrain/obstacles/rock samples
    threshed = color_thresh(warped)

    # 4) Update Rover.vision_image (this will be displayed on left side of screen)
    Rover.vision_image[:,:,0] = threshed[:,:,0]*mask
    Rover.vision_image[:,:,1] = threshed[:,:,1]
    Rover.vision_image[:,:,2] = threshed[:,:,2]

    # 5) Convert map image pixel values to rover-centric coords
    x_terrain_rover, y_terrain_rover = rover_coords(threshed[:,:,2])
    x_rock_rover, y_rock_rover = rover_coords(threshed[:,:,1])
    x_obstacle_rover, y_obstacle_rover = rover_coords(threshed[:,:,0])

    # 6) Convert rover-centric pixel values to world coordinates

    x_,y_ = Rover.pos
    yaw_ = Rover.yaw
    
    world_size = 200
    scale = 10

    navigable_x_world, navigable_y_world = pix_to_world(x_terrain_rover, y_terrain_rover, x_, y_, yaw_, world_size, scale)
    rock_x_world, rock_y_world = pix_to_world(x_rock_rover, y_rock_rover, x_, y_, yaw_, world_size, scale)
    obstacle_x_world, obstacle_y_world = pix_to_world(x_obstacle_rover, y_obstacle_rover, x_, y_, y_, world_size, scale)

    # 7) Update Rover worldmap (to be displayed on right side of screen)
    
    if( ((Rover.pitch >= 359.5) | (Rover.pitch <= 0.5)) & ((Rover.roll >= 359.5) | (Rover.roll <= 0.5)) ):
        
        Rover.worldmap[obstacle_y_world, obstacle_x_world, 0] += 1
        Rover.worldmap[rock_y_world, rock_x_world, 1] += 1
        Rover.worldmap[navigable_y_world, navigable_x_world, 2] += 1

    # 8) Convert rover-centric pixel positions to polar coordinates
           
    if x_rock_rover.any():        
        dist, angles = to_polar_coords(x_rock_rover, y_rock_rover)    
        Rover.nav_dists = dist
        Rover.nav_angles = angles
        Rover.stop_forward = 5  
        Rover.go_forward = 500           
    else:
        dist, angles = to_polar_coords(x_terrain_rover, y_terrain_rover)
        Rover.nav_dists = dist
        Rover.nav_angles = angles     
        Rover.stop_forward = 20
        Rover.go_forward = 1000 
     # Update Rover pixel distances and angles

                
    return Rover
