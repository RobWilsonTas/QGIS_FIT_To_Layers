import sys, subprocess
from pathlib import Path

#Install fitparse if it doesn't already exist
try:
    import fitparse
except ImportError:
    print("fitparse not found, installing now")
    pythonExeForQgis = str(Path(QgsApplication.prefixPath()).parent.parent) + r"\apps\Python312\python.exe"
    subprocess.run([pythonExeForQgis, "-m", "pip", "install", "fitparse"])

from qgis.core import QgsProcessingAlgorithm, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsField, QgsProject, QgsProcessing, QgsProcessingParameterString
from PyQt5.QtCore import QVariant
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from fitparse import FitFile
from datetime import timedelta
import processing

class FitFilesToPaths(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        
        #No input parameter here, for some reason QGIS doesn't allow you to select multiple files in the initAlgorithm
        self.addParameter(QgsProcessingParameterString(
            "info","Text box",defaultValue="Click run and you'll be prompted to select one or more .fit files",multiLine=True,optional=True))
        
    def processAlgorithm(self, parameters, context, feedback):
        
        #Ask the user to select multiple .fit files
        fitFiles, _ = QFileDialog.getOpenFileNames(None, "Select FIT files", "S:/Current Jobs/", "FIT Files (*.fit)")
        if not fitFiles:
            feedback.reportError("No files selected?")
            return {}

        #Go through each fit file selected
        for fitFilePath in fitFiles:
            feedback.pushInfo("Processing file: " + fitFilePath)
            gpsData = FitFile(fitFilePath)

            #Make a temporary memory layer for points
            tempPointLayer = QgsVectorLayer("Point?crs=EPSG:4326", fitFilePath.split("\\")[-1], "memory")
            layerProvider = tempPointLayer.dataProvider()
            
            #Add columns: timestamp and session ID for keeping track of the sections of recording
            layerProvider.addAttributes([QgsField("timestamp", QVariant.String), QgsField("session", QVariant.Int)])
            tempPointLayer.updateFields()

            #Keep track of the points
            allPoints = []
            lastTime = None
            currentSession = 1

            #Go through every point
            for trackPoint in gpsData.get_messages("record"):
                lat = None
                lon = None
                timestamp = None
                
                #Get all the attributes out
                for field in trackPoint:
                    if field.name == "position_lat" and field.value is not None:
                        lat=field.value*(180/2**31)
                    if field.name == "position_long" and field.value is not None:
                        lon=field.value*(180/2**31)
                    if field.name=="timestamp":
                        timestamp = field.value

                #Only keep valid points with a location and time stamp
                if lat is not None and lon is not None and timestamp is not None:
                    
                    #If more than 10 minutes have passed since the last point, start a new session
                    if lastTime is not None and (timestamp - lastTime) > timedelta(minutes=10):
                        currentSession += 1
                    lastTime = timestamp

                    #Create a point base on what we have so far
                    pointFeature = QgsFeature()
                    pointFeature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
                    pointFeature.setAttributes([str(timestamp), currentSession])
                    allPoints.append(pointFeature)

            #Add all the points together
            layerProvider.addFeatures(allPoints)
            tempPointLayer.updateExtents()

            #Convert points to lines, grouped by session so we don't have massive lines flying across the state
            pathLayer = processing.run("native:pointstopath", {'INPUT': tempPointLayer, 'CLOSE_PATH': False, 'ORDER_EXPRESSION': '"timestamp"',
                'NATURAL_SORT': False, 'GROUP_EXPRESSION': '"session"', 'OUTPUT': 'TEMPORARY_OUTPUT'}, context=context, feedback=feedback)['OUTPUT']

            #Add the resulting line layer to the project
            QgsProject.instance().addMapLayer(pathLayer)

        #Return nothing because you need to return something
        return {}

    #Required bs
    def name(self): return 'fitfiles_to_paths'
    def displayName(self): return 'FIT Files To Paths'
    def group(self): return 'NB Custom Scripts'
    def groupId(self): return 'nbcustomscripts'
    def createInstance(self): return FitFilesToPaths()