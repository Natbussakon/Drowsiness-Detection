import cv2
import numpy as np
import os
from scipy.spatial import distance as dist
from imutils.video import VideoStream
from imutils import face_utils
from threading import Thread,Timer
import playsound
import argparse
import imutils
import time
import dlib

from matplotlib import pyplot as plt, cm, colors

ym_per_pix = 30 / 720

xm_per_pix = 3.7 / 720

CWD_PATH = os.getcwd()
start = 1
#eyes detect
def sound_alarm(path):
    # play an alarm sound
    playsound.playsound(path)


def eye_aspect_ratio(eye):
    # compute the euclidean distances between the two sets of
    # vertical eye landmarks (x, y)-coordinates
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])

    # compute the euclidean distance between the horizontal
    # eye landmark (x, y)-coordinates
    C = dist.euclidean(eye[0], eye[3])

    # compute the eye aspect ratio
    ear = (A + B) / (2.0 * C)

    # return the eye aspect ratio
    return ear
EYE_AR_THRESH = 0.3
EYE_AR_CONSEC_FRAMES = 30
COUNTER = 0

ALARM_ON = False
ChangeLane = 0
print("[INFO] loading facial landmark predictor...")
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor("shape_predictor_68_face_landmarks.dat")
(lStart, lEnd) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
(rStart, rEnd) = face_utils.FACIAL_LANDMARKS_IDXS["right_eye"]
print("[INFO] starting video stream thread...")
vs = VideoStream(src=0).start()
time.sleep(1.0)



def readVideo():
    # Read input video from current working directory
    inpImage = cv2.VideoCapture(os.path.join(CWD_PATH, 'car10.mp4'))

    return inpImage


################################################################################
#### START - FUNCTION TO PROCESS IMAGE #########################################
def processImage(inpImage):
    # Apply HLS color filtering to filter out white lane lines
    hls = cv2.cvtColor(inpImage, cv2.COLOR_BGR2HLS)
    lower_white = np.array([0, 160, 10])
    upper_white = np.array([255, 255, 255])
    mask = cv2.inRange(inpImage, lower_white, upper_white)
    hls_result = cv2.bitwise_and(inpImage, inpImage, mask=mask)

    # Convert image to grayscale, apply threshold, blur & extract edges
    gray = cv2.cvtColor(hls_result, cv2.COLOR_BGR2GRAY)
    ret, thresh = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
    blur = cv2.GaussianBlur(thresh, (3, 3), 0)
    canny = cv2.Canny(blur, 40, 60)

    # Display the processed images
    #    cv2.imshow("Image", inpImage)
    #    cv2.imshow("HLS Filtered", hls_result)
    #   cv2.imshow("Grayscale", gray)
    #   cv2.imshow("Thresholded", thresh)
    #cv2.imshow("Blurred", blur)
    #cv2.imshow("Canny Edges", canny)

    return image, hls_result, gray, thresh, blur, canny


#### END - FUNCTION TO PROCESS IMAGE ###########################################
################################################################################


################################################################################
#### START - FUNCTION TO APPLY PERSPECTIVE WARP ################################
def perspectiveWarp(inpImage):
    # print(str(inpImage.shape[0]))
    # Get image size
    img_size = (inpImage.shape[1], inpImage.shape[0])

    # Perspective points to be warped

    src = np.float32([[ 555 , 478 ],
[ 734 , 479 ],
[ 317 , 618 ],
[ 884 , 626 ]])

    '''
    src = np.float32([[580, 408],
                      [743, 408],
                      [218, 651],
                      [1105, 631]])'''
    polygons = np.array([[ 555 , 478 ],
[ 734 , 479 ],
[ 884 , 626 ],
[317, 618]])
    mask = np.zeros_like(frame)
    cv2.fillConvexPoly(mask, polygons, 255)
    show = cv2.addWeighted(frame, 0.5, mask, 0.5, 0)
    #cv2.imshow("poly", show)
    # src = np.float32([[711, 392], [591, 384], [924, 559],[353, 539]])

    # Window to be shown
    dst = np.float32([[200, 0],
                      [1200, 0],
                      [200, 710],
                      [1200, 710]])

    # Matrix to warp the image for birdseye window
    matrix = cv2.getPerspectiveTransform(src, dst)
    # Inverse matrix to unwarp the image for final window
    minv = cv2.getPerspectiveTransform(dst, src)
    birdseye = cv2.warpPerspective(inpImage, matrix, img_size)

    # Get the birdseye window dimensions
    height, width = birdseye.shape[:2]

    # Divide the birdseye view into 2 halves to separate left & right lanes
    birdseyeLeft = birdseye[0:height, 0:width // 2]
    birdseyeRight = birdseye[0:height, width // 2:width]

    # Display birdseye view image

    #cv2.imshow("Birdseye" , birdseye)
    #cv2.imshow("Birdseye Left" , birdseyeLeft)
    #cv2.imshow("Birdseye Right", birdseyeRight)

    return birdseye, birdseyeLeft, birdseyeRight, minv


#### END - FUNCTION TO APPLY PERSPECTIVE WARP ##################################
################################################################################


################################################################################
#### START - FUNCTION TO PLOT THE HISTOGRAM OF WARPED IMAGE ####################
def plotHistogram(inpImage):
    histogram = np.sum(inpImage[inpImage.shape[0] // 2:, :], axis=0)

    midpoint = np.int(histogram.shape[0] / 2)
    leftxBase = np.argmax(histogram[:midpoint])
    rightxBase = np.argmax(histogram[midpoint:]) + midpoint

    plt.xlabel("Image X Coordinates")
    plt.ylabel("Number of White Pixels")

    # Return histogram and x-coordinates of left & right lanes to calculate
    # lane width in pixels
    return histogram, leftxBase, rightxBase


#### END - FUNCTION TO PLOT THE HISTOGRAM OF WARPED IMAGE ######################
################################################################################


################################################################################
#### START - APPLY SLIDING WINDOW METHOD TO DETECT CURVES ######################


def slide_window_search(binary_warped, histogram):
    global last_left_lane_inds
    global last_right_lane_inds
    global last_nonzerox
    global last_nonzeroy
    global ChangeLane

    # Find the start of left and right lane lines using histogram info
    out_img = np.dstack((binary_warped, binary_warped, binary_warped)) * 255
    midpoint = np.int(histogram.shape[0] / 2)
    leftx_base = np.argmax(histogram[:midpoint])
    rightx_base = np.argmax(histogram[midpoint:]) + midpoint

    # A total of 9 windows will be used
    nwindows = 9
    window_height = np.int(binary_warped.shape[0] / nwindows)
    nonzero = binary_warped.nonzero()
    nonzeroy = np.array(nonzero[0])
    nonzerox = np.array(nonzero[1])
    leftx_current = leftx_base
    rightx_current = rightx_base
    margin = 100
    minpix = 50
    left_lane_inds = []
    right_lane_inds = []

    #### START - Loop to iterate through windows and search for lane lines #####
    for window in range(nwindows):
        win_y_low = binary_warped.shape[0] - (window + 1) * window_height
        win_y_high = binary_warped.shape[0] - window * window_height
        win_xleft_low = leftx_current - margin
        win_xleft_high = leftx_current + margin
        win_xright_low = rightx_current - margin
        win_xright_high = rightx_current + margin
        cv2.rectangle(out_img, (win_xleft_low, win_y_low), (win_xleft_high, win_y_high),
                      (0, 255, 0), 2)
        cv2.rectangle(out_img, (win_xright_low, win_y_low), (win_xright_high, win_y_high),
                      (0, 255, 0), 2)
        good_left_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
                          (nonzerox >= win_xleft_low) & (nonzerox < win_xleft_high)).nonzero()[0]
        good_right_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
                           (nonzerox >= win_xright_low) & (nonzerox < win_xright_high)).nonzero()[0]
        left_lane_inds.append(good_left_inds)
        right_lane_inds.append(good_right_inds)
        if len(good_left_inds) > minpix:
            leftx_current = np.int(np.mean(nonzerox[good_left_inds]))
        if len(good_right_inds) > minpix:
            rightx_current = np.int(np.mean(nonzerox[good_right_inds]))
    #### END - Loop to iterate through windows and search for lane lines #######

    left_lane_inds = np.concatenate(left_lane_inds)
    right_lane_inds = np.concatenate(right_lane_inds)

    if (left_lane_inds.size != 0 and right_lane_inds.size != 0):
        last_left_lane_inds = left_lane_inds
        last_right_lane_inds = right_lane_inds  # test
        last_nonzerox = nonzerox
        last_nonzeroy = nonzeroy

    # print("save left ="+str(left_lane_inds)+" right="+str(right_lane_inds))
    else:
        left_lane_inds = last_left_lane_inds
        right_lane_inds = last_right_lane_inds  # test
        nonzerox = last_nonzerox
        nonzeroy = last_nonzeroy
        cv2.putText(frame, "Change Lane !", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        ChangeLane = 1
        g = Timer(3.0, backtolane)
        g.start()
    # print("Left lane is disappear !")

    # print(str(left_lane_inds)+"left")
    # print(str(right_lane_inds)+"right")
    # print(str(nonzerox[left_lane_inds]))
    leftx = nonzerox[left_lane_inds]
    lefty = nonzeroy[left_lane_inds]
    rightx = nonzerox[right_lane_inds]
    righty = nonzeroy[right_lane_inds]
    # add
    # Apply 2nd degree polynomial fit to fit curves

    left_fit = np.polyfit(lefty, leftx, 2)
    right_fit = np.polyfit(righty, rightx, 2)

    ploty = np.linspace(0, binary_warped.shape[0] - 1, binary_warped.shape[0])
    left_fitx = left_fit[0] * ploty ** 2 + left_fit[1] * ploty + left_fit[2]
    right_fitx = right_fit[0] * ploty ** 2 + right_fit[1] * ploty + right_fit[2]

    ltx = np.trunc(left_fitx)
    rtx = np.trunc(right_fitx)
    plt.plot(right_fitx)
    # plt.show()

    out_img[nonzeroy[left_lane_inds], nonzerox[left_lane_inds]] = [255, 0, 0]
    out_img[nonzeroy[right_lane_inds], nonzerox[right_lane_inds]] = [0, 0, 255]

    # plt.imshow(out_img)
    plt.plot(left_fitx, ploty, color='yellow')
    plt.plot(right_fitx, ploty, color='yellow')
    plt.xlim(0, 1280)
    plt.ylim(720, 0)

    return ploty, left_fit, right_fit, ltx, rtx


#### END - APPLY SLIDING WINDOW METHOD TO DETECT CURVES ########################
################################################################################


################################################################################
#### START - APPLY GENERAL SEARCH METHOD TO DETECT CURVES ######################
def backtolane():
    global ChangeLane
    ChangeLane = 0
def general_search(binary_warped, left_fit, right_fit):
    global last_leftx
    global last_rightx
    global last_lefty
    global last_righty
    global ChangeLane
    nonzero = binary_warped.nonzero()
    nonzeroy = np.array(nonzero[0])
    nonzerox = np.array(nonzero[1])
    margin = 100
    left_lane_inds = ((nonzerox > (left_fit[0] * (nonzeroy ** 2) + left_fit[1] * nonzeroy +
                                   left_fit[2] - margin)) & (nonzerox < (left_fit[0] * (nonzeroy ** 2) +
                                                                         left_fit[1] * nonzeroy + left_fit[
                                                                             2] + margin)))

    right_lane_inds = ((nonzerox > (right_fit[0] * (nonzeroy ** 2) + right_fit[1] * nonzeroy +
                                    right_fit[2] - margin)) & (nonzerox < (right_fit[0] * (nonzeroy ** 2) +
                                                                           right_fit[1] * nonzeroy + right_fit[
                                                                               2] + margin)))

    # add

    leftx = nonzerox[left_lane_inds]
    lefty = nonzeroy[left_lane_inds]
    rightx = nonzerox[right_lane_inds]
    righty = nonzeroy[right_lane_inds]
    # print("leftx = "+str(leftx))
    # print("leftx size = "+str(leftx.size))
    if (leftx.size != 0 and rightx.size != 0 and lefty.size != 0 and righty.size != 0):
        last_leftx = leftx
        last_rightx = rightx  # test
        last_lefty = lefty
        last_righty = righty


    else:
        leftx = last_leftx
        rightx = last_rightx  # test
        lefty = last_lefty
        righty = last_righty
        print("update" + str(leftx))
        print("Left lane is disappear !")
        cv2.putText(frame, "Change Lane !", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        ChangeLane = 1
        s = Timer(3.0,backtolane)
        s.start()


    left_fit = np.polyfit(lefty, leftx, 2)

    right_fit = np.polyfit(righty, rightx, 2)
    ploty = np.linspace(0, binary_warped.shape[0] - 1, binary_warped.shape[0])
    left_fitx = left_fit[0] * ploty ** 2 + left_fit[1] * ploty + left_fit[2]
    right_fitx = right_fit[0] * ploty ** 2 + right_fit[1] * ploty + right_fit[2]

    ## VISUALIZATION ###########################################################

    out_img = np.dstack((binary_warped, binary_warped, binary_warped)) * 255
    window_img = np.zeros_like(out_img)
    out_img[nonzeroy[left_lane_inds], nonzerox[left_lane_inds]] = [255, 0, 0]
    out_img[nonzeroy[right_lane_inds], nonzerox[right_lane_inds]] = [0, 0, 255]

    left_line_window1 = np.array([np.transpose(np.vstack([left_fitx - margin, ploty]))])
    left_line_window2 = np.array([np.flipud(np.transpose(np.vstack([left_fitx + margin,
                                                                    ploty])))])
    left_line_pts = np.hstack((left_line_window1, left_line_window2))
    right_line_window1 = np.array([np.transpose(np.vstack([right_fitx - margin, ploty]))])
    right_line_window2 = np.array([np.flipud(np.transpose(np.vstack([right_fitx + margin, ploty])))])
    right_line_pts = np.hstack((right_line_window1, right_line_window2))

    cv2.fillPoly(window_img, np.int_([left_line_pts]), (0, 255, 0))
    cv2.fillPoly(window_img, np.int_([right_line_pts]), (0, 255, 0))
    result = cv2.addWeighted(out_img, 1, window_img, 0.3, 0)

    # plt.imshow(result)
    plt.plot(left_fitx, ploty, color='yellow')
    plt.plot(right_fitx, ploty, color='yellow')
    plt.xlim(0, 1280)
    plt.ylim(720, 0)

    ret = {}
    ret['leftx'] = leftx
    ret['rightx'] = rightx
    ret['left_fitx'] = left_fitx
    ret['right_fitx'] = right_fitx
    ret['ploty'] = ploty

    return ret


#### END - APPLY GENERAL SEARCH METHOD TO DETECT CURVES ########################
################################################################################


################################################################################
#### START - FUNCTION TO MEASURE CURVE RADIUS ##################################
def measure_lane_curvature(ploty, leftx, rightx):
    leftx = leftx[::-1]  # Reverse to match top-to-bottom in y
    rightx = rightx[::-1]  # Reverse to match top-to-bottom in y

    # Choose the maximum y-value, corresponding to the bottom of the image
    y_eval = np.max(ploty)

    # Fit new polynomials to x, y in world space
    left_fit_cr = np.polyfit(ploty * ym_per_pix, leftx * xm_per_pix, 2)
    right_fit_cr = np.polyfit(ploty * ym_per_pix, rightx * xm_per_pix, 2)

    # Calculate the new radii of curvature
    left_curverad = ((1 + (2 * left_fit_cr[0] * y_eval * ym_per_pix + left_fit_cr[1]) ** 2) ** 1.5) / np.absolute(
        2 * left_fit_cr[0])
    right_curverad = ((1 + (2 * right_fit_cr[0] * y_eval * ym_per_pix + right_fit_cr[1]) ** 2) ** 1.5) / np.absolute(
        2 * right_fit_cr[0])

    # Now our radius of curvature is in meters
    # print(left_curverad, 'm', right_curverad, 'm')

    # Decide if it is a left or a right curve
    if leftx[0] - leftx[-1] > 60:
        curve_direction = 'Left Curve'
    elif leftx[-1] - leftx[0] > 60:
        curve_direction = 'Right Curve'
    else:
        curve_direction = 'Straight'

    return (left_curverad + right_curverad) / 2.0, curve_direction


#### END - FUNCTION TO MEASURE CURVE RADIUS ####################################
################################################################################


################################################################################
#### START - FUNCTION TO VISUALLY SHOW DETECTED LANES AREA #####################
def draw_lane_lines(original_image, warped_image, Minv, draw_info):
    leftx = draw_info['leftx']
    rightx = draw_info['rightx']
    left_fitx = draw_info['left_fitx']
    right_fitx = draw_info['right_fitx']
    ploty = draw_info['ploty']

    warp_zero = np.zeros_like(warped_image).astype(np.uint8)
    color_warp = np.dstack((warp_zero, warp_zero, warp_zero))

    pts_left = np.array([np.transpose(np.vstack([left_fitx, ploty]))])
    pts_right = np.array([np.flipud(np.transpose(np.vstack([right_fitx, ploty])))])
    pts = np.hstack((pts_left, pts_right))

    mean_x = np.mean((left_fitx, right_fitx), axis=0)
    pts_mean = np.array([np.flipud(np.transpose(np.vstack([mean_x, ploty])))])

    cv2.fillPoly(color_warp, np.int_([pts]), (0, 255, 0))
    cv2.fillPoly(color_warp, np.int_([pts_mean]), (0, 255, 255))

    newwarp = cv2.warpPerspective(color_warp, Minv, (original_image.shape[1], original_image.shape[0]))
    result = cv2.addWeighted(original_image, 1, newwarp, 0.3, 0)

    return pts_mean, result


#### END - FUNCTION TO VISUALLY SHOW DETECTED LANES AREA #######################
################################################################################


#### START - FUNCTION TO CALCULATE DEVIATION FROM LANE CENTER ##################
################################################################################
def offCenter(meanPts, inpFrame):
    # Calculating deviation in meters
    mpts = meanPts[-1][-1][-2].astype(int)
    pixelDeviation = inpFrame.shape[1] / 2 - abs(mpts)
    deviation = pixelDeviation * xm_per_pix
    direction = "left" if deviation < 0 else "right"

    return deviation, direction


################################################################################
#### END - FUNCTION TO CALCULATE DEVIATION FROM LANE CENTER ####################


################################################################################
#### START - FUNCTION TO ADD INFO TEXT TO FINAL IMAGE ##########################
def addText(img, radius, direction, deviation, devDirection):
    # Add the radius and center position to the image
    font = cv2.FONT_HERSHEY_TRIPLEX

    if (direction != 'Straight'):
        text = 'Radius of Curvature: ' + '{:04.0f}'.format(radius) + 'm'
        text1 = 'Curve Direction: ' + (direction)

    else:
        text = 'Radius of Curvature: ' + 'N/A'
        text1 = 'Curve Direction: ' + (direction)

    cv2.putText(img, text, (50, 100), font, 0.8, (0, 100, 200), 2, cv2.LINE_AA)
    cv2.putText(img, text1, (50, 150), font, 0.8, (0, 100, 200), 2, cv2.LINE_AA)

    # Deviation
    deviation_text = 'Off Center: ' + str(round(abs(deviation), 3)) + 'm' + ' to the ' + devDirection
    cv2.putText(img, deviation_text, (50, 200), cv2.FONT_HERSHEY_TRIPLEX, 0.8, (0, 100, 200), 2, cv2.LINE_AA)

    return img


#### END - FUNCTION TO ADD INFO TEXT TO FINAL IMAGE ############################
################################################################################

################################################################################
######## END - FUNCTIONS TO PERFORM IMAGE PROCESSING ###########################
################################################################################

################################################################################
################################################################################
################################################################################
################################################################################

################################################################################
######## START - MAIN FUNCTION #################################################
################################################################################

# Read the input image
image = readVideo()
def AlarmBack():
    global ALARM_ON
    ALARM_ON = False
################################################################################
#### START - LOOP TO PLAY THE INPUT IMAGE ######################################
SLEEP = False
while True:
    #Eyes
    frame2 = vs.read()
    frame2 = imutils.resize(frame2, width=450)
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
    rects = detector(gray2, 0)
    for rect in rects:
        # determine the facial landmarks for the face region, then
        # convert the facial landmark (x, y)-coordinates to a NumPy
        # array
        shape = predictor(gray2, rect)
        shape = face_utils.shape_to_np(shape)

        # extract the left and right eye coordinates, then use the
        # coordinates to compute the eye aspect ratio for both eyes
        leftEye = shape[lStart:lEnd]
        rightEye = shape[rStart:rEnd]
        leftEAR = eye_aspect_ratio(leftEye)
        rightEAR = eye_aspect_ratio(rightEye)

        # average the eye aspect ratio together for both eyes
        ear = (leftEAR + rightEAR) / 2.0

        # compute the convex hull for the left and right eye, then
        # visualize each of the eyes
        leftEyeHull = cv2.convexHull(leftEye)
        rightEyeHull = cv2.convexHull(rightEye)
        # cv2.drawContours(frame, [leftEyeHull], -1, (0, 255, 0), 1)
        # cv2.drawContours(frame, [rightEyeHull], -1, (0, 255, 0), 1)

        # check to see if the eye aspect ratio is below the blink
        # threshold, and if so, increment the blink frame counter
        print(str(COUNTER))
        if ear < EYE_AR_THRESH:
            COUNTER += 1


            # if the eyes were closed for a sufficient number of
            # then sound the alarm
            if COUNTER >= EYE_AR_CONSEC_FRAMES and ChangeLane == 1:
                SLEEP = True


        # otherwise, the eye aspect ratio is not below the blink
        # threshold, so reset the counter and alarm
        else:
            COUNTER = 0
            ALARM_ON = False
            SLEEP = False

        if SLEEP == True:
            cv2.putText(frame2, "DROWSINESS ALERT!", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            if not ALARM_ON :
                ALARM_ON = True

                # check to see if an alarm file was supplied,
                # and if so, start a thread to have the alarm
                # sound played in the background

                t = Thread(target=sound_alarm,
                           args=("alarm.wav",))
                t.deamon = True
                t.start()
                k = Timer(3.0, AlarmBack)
                k.start()
        # draw the computed eye aspect ratio on the frame to help
        # with debugging and setting the correct eye aspect ratio
        # thresholds and frame counters
        cv2.putText(frame2, "EAR: {:.2f}".format(ear), (300, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)


    # show the frame
    #cv2.imshow("Frame", frame2)

    #endEyes
    _, frame = image.read()

    # Apply perspective warping by calling the "perspectiveWarp()" function
    # Then assign it to the variable called (birdView)
    # Provide this function with:
    # 1- an image to apply perspective warping (frame)
    birdView, birdViewL, birdViewR, minverse = perspectiveWarp(frame)

    # Apply image processing by calling the "processImage()" function
    # Then assign their respective variables (img, hls, grayscale, thresh, blur, canny)
    # Provide this function with:
    # 1- an already perspective warped image to process (birdView)
    img, hls, grayscale, thresh, blur, canny = processImage(birdView)
    imgL, hlsL, grayscaleL, threshL, blurL, cannyL = processImage(birdViewL)
    imgR, hlsR, grayscaleR, threshR, blurR, cannyR = processImage(birdViewR)

    # Plot and display the histogram by calling the "get_histogram()" function
    # Provide this function with:
    # 1- an image to calculate histogram on (thresh)
    hist, leftBase, rightBase = plotHistogram(thresh)
    # print(rightBase - leftBase)
    plt.plot(hist)
    # plt.show()

    ploty, left_fit, right_fit, left_fitx, right_fitx = slide_window_search(thresh, hist)
    # print(str(ploty)+" "+ str(left_fit)+" " +str(right_fit)+" " + str(left_fitx)+" "+str( right_fitx) )
    plt.plot(left_fit)
    # plt.show()

    draw_info = general_search(thresh, left_fit, right_fit)
    # plt.show()

    curveRad, curveDir = measure_lane_curvature(ploty, left_fitx, right_fitx)

    # Filling the area of detected lanes with green
    meanPts, result = draw_lane_lines(frame, thresh, minverse, draw_info)

    deviation, directionDev = offCenter(meanPts, frame)

    # Adding text to our final image
    finalImg = addText(result, curveRad, curveDir, deviation, directionDev)

    # Displaying final image
    cv2.imshow("Final", finalImg)
    cv2.imshow("Frame", frame2)
    # Wait for the ENTER key to be pressed to stop playback
    if cv2.waitKey(1) == 13:
        break

#### END - LOOP TO PLAY THE INPUT IMAGE ########################################
################################################################################

# Cleanup
image.release()
cv2.destroyAllWindows()

################################################################################
######## END - MAIN FUNCTION ###################################################
#########################################perspectiveWarp#######################################


##
