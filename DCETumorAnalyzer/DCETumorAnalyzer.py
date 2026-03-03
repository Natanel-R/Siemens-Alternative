import logging
import os
from typing import Annotated

import vtk, qt, ctk

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)
from slicer import vtkMRMLScalarVolumeNode

try:
    import matplotlib
except ModuleNotFoundError:
    print("Matplotlib not found. Installing into Slicer environment. This may take a minute...")
    slicer.util.pip_install("matplotlib")
    import matplotlib
#
# DCETumorAnalyzer
#

class DCETumorAnalyzer(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("DCETumorAnalyzer")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = []
        self.parent.contributors = ["John Doe (AnyWare Corp.)"]
        self.parent.helpText = _("""
This is an example of scripted loadable module bundled in an extension.
""")
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")
        slicer.app.connect("startupCompleted()", registerSampleData)


def registerSampleData():
    import SampleData
    iconsPath = os.path.join(os.path.dirname(__file__), "Resources/Icons")
    
    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        category="DCETumorAnalyzer",
        sampleName="DCETumorAnalyzer1",
        thumbnailFileName=os.path.join(iconsPath, "DCETumorAnalyzer1.png"),
        uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
        fileNames="DCETumorAnalyzer1.nrrd",
        checksums="SHA256:998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
        nodeNames="DCETumorAnalyzer1",
    )


@parameterNodeWrapper
class DCETumorAnalyzerParameterNode:
    inputVolume: vtkMRMLScalarVolumeNode
    imageThreshold: Annotated[float, WithinRange(-100, 500)] = 100
    invertThreshold: bool = False
    thresholdedVolume: vtkMRMLScalarVolumeNode
    invertedVolume: vtkMRMLScalarVolumeNode


class DCETumorAnalyzerWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None) -> None:
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.logic = DCETumorAnalyzerLogic()
        # Create a variable to track our drawing node
        self._segmentationNode = None

    def setup(self) -> None:
        try:
            # Hide Slicer's global Data Probe at the bottom of the screen
            mainWindow = slicer.util.mainWindow()
            if mainWindow:
                for child in mainWindow.findChildren("ctkCollapsibleButton"):
                    if child.text == "Data Probe":
                        child.hide()
        except Exception as e:
            print(f"Could not hide global widgets: {e}")

        # --- 2. FLAT RELOAD BUTTON ---
        self.reloadButton = qt.QPushButton("Reload Script")
        self.reloadButton.setStyleSheet("background-color: #555555; color: white; margin-bottom: 15px; height: 30px;")
        self.reloadButton.clicked.connect(self.onReload)
        self.layout.addWidget(self.reloadButton)

        # --- 3. FLAT DATA INPUT ---
        inputLayout = qt.QFormLayout()
        self.inputDirSelector = ctk.ctkPathLineEdit()
        self.inputDirSelector.filters = ctk.ctkPathLineEdit.Dirs
        inputLayout.addRow("Folder:", self.inputDirSelector)
        self.layout.addLayout(inputLayout)

        self.processButton = qt.QPushButton("Load MRI Scan")
        self.processButton.setStyleSheet("font-weight: bold; height: 35px; background-color: #34495e; color: white; margin-bottom: 20px;")
        self.processButton.clicked.connect(self.onProcessButton)
        self.layout.addWidget(self.processButton)

        self.loadSavedButton = qt.QPushButton("Load Saved Patient Analysis")
        self.loadSavedButton.setStyleSheet("font-weight: bold; height: 35px; background-color: #8e44ad; color: white; margin-bottom: 20px;")
        self.loadSavedButton.clicked.connect(self.onLoadSavedButton)
        self.layout.addWidget(self.loadSavedButton)

        self.clearButton = qt.QPushButton("Clear Scene & Reset")
        self.clearButton.setStyleSheet("font-weight: bold; height: 35px; background-color: #c0392b; color: white; margin-bottom: 20px;")
        self.clearButton.clicked.connect(self.onClearButton)
        self.layout.addWidget(self.clearButton)

        # --- 4. FLAT TUMOR MARKING (Just the Tools) ---
        self.segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()
        self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        
        # Give it a brain immediately
        editorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
        self.segmentEditorWidget.setMRMLSegmentEditorNode(editorNode)
        
        # Strip away the Slicer dropdowns and junk
        self.segmentEditorWidget.setSegmentationNodeSelectorVisible(False)
        self.segmentEditorWidget.setSourceVolumeNodeSelectorVisible(False)
        self.segmentEditorWidget.setSwitchToSegmentationsButtonVisible(False)
        
        # Only show Paint and Erase icons
        self.segmentEditorWidget.setEffectNameOrder(['Paint', 'Erase'])
        self.segmentEditorWidget.unorderedEffectsVisible = False
        
        self.layout.addWidget(self.segmentEditorWidget)

        # --- 5. FLAT ANALYSIS RESULTS ---
        self.analyzeButton = qt.QPushButton("Calculate Tumor Density")
        self.analyzeButton.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; height: 40px; margin-top: 20px;")
        self.analyzeButton.clicked.connect(self.onAnalyzeButton)
        self.layout.addWidget(self.analyzeButton)

        self.resultsTextBox = qt.QTextEdit()
        self.resultsTextBox.setReadOnly(True)
        self.resultsTextBox.setFixedHeight(80)
        self.resultsTextBox.setStyleSheet("background-color: #1e1e1e; color: #2ecc71; font-family: monospace;")
        self.layout.addWidget(self.resultsTextBox)

        self.layout.addStretch(1)

    def onReload(self):
        print("\n--- Reloading Module ---")
        slicer.util.reloadScriptedModule("DCETumorAnalyzer")

    def onProcessButton(self):
        print("\033[H\033[J", end="") 
        try:
            path = self.inputDirSelector.currentPath
            if not path:
                slicer.util.errorDisplay("Please select a directory first!")
                return
            
            # Wipe memory and load data
            slicer.mrmlScene.Clear()
            self.logic.load_dce_data(path)
            slicer.app.processEvents()
            
            mri_node = slicer.mrmlScene.GetFirstNodeByName("10: B0")
            
            if mri_node:
                # Re-link the UI
                self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
                editorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
                self.segmentEditorWidget.setMRMLSegmentEditorNode(editorNode)

                # Create the Canvas
                seg_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "My_Tumor_Drawings")
                self.segmentEditorWidget.setSegmentationNode(seg_node)
                self.segmentEditorWidget.setSourceVolumeNode(mri_node)
                
                # --- THE FIX FOR THE "GHOST BRUSH" ---
                # We physically create a layer in memory for the paint to stick to
                seg_node.GetSegmentation().AddEmptySegment("TumorLayer")
                
                # Now when we activate Paint, it will actually work
                self.segmentEditorWidget.setActiveEffectByName("Paint")
                
                print("UI ready. You can now paint on the slices.")
                
        except Exception as e:
            slicer.util.errorDisplay(f"Load failed: {e}")

    def onLoadSavedButton(self):
        import os
        print("\033[H\033[J", end="") 
        try:
            path = self.inputDirSelector.currentPath
            if not path:
                slicer.util.errorDisplay("Please select a patient directory first!")
                return
            
            mask_path = os.path.join(path, "Analysis_Results", "tumor_mask.seg.nrrd")
            
            if not os.path.exists(mask_path):
                slicer.util.errorDisplay("No saved analysis found in this folder.\n(Could not find tumor_mask.seg.nrrd)")
                return

            self.resultsTextBox.setPlainText("Loading saved patient data...")
            slicer.app.processEvents()

            # 1. Clear memory and load the raw MRI scans
            slicer.mrmlScene.Clear()
            self.logic.load_dce_data(path)
            slicer.app.processEvents()

            # 2. Load the saved mask and rename it so our math engine recognizes it
            seg_node = slicer.util.loadSegmentation(mask_path)
            seg_node.SetName("My_Tumor_Drawings")

            # 3. Re-link the UI so they can edit the mask if they want to
            mri_node = slicer.mrmlScene.GetFirstNodeByName("10: B0")
            if mri_node:
                self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
                editorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
                self.segmentEditorWidget.setMRMLSegmentEditorNode(editorNode)
                self.segmentEditorWidget.setSegmentationNode(seg_node)
                self.segmentEditorWidget.setSourceVolumeNode(mri_node)

            # 4. Automatically trigger the math engine and open the dashboard!
            self.onAnalyzeButton()
            
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load saved data: {e}")
    
    def onClearButton(self):
        import slicer
        
        # 1. Ask Slicer to completely flush the C++ memory
        slicer.mrmlScene.Clear(0)
        
        # 2. Reset the UI Text Box
        self.resultsTextBox.setPlainText("Memory cleared. Ready for the next patient.")
        
        # 3. Disconnect the Segment Editor so it doesn't hold onto dead memory pointers
        self.segmentEditorWidget.setMRMLScene(None)
        self.segmentEditorWidget.setSegmentationNode(None)
        self.segmentEditorWidget.setSourceVolumeNode(None)
        
        # Reconnect it to the fresh, empty scene
        self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        
        # Clear the Python console for a fresh start
        print("\033[H\033[J", end="") 
        print("--- RAM FLUSHED: READY FOR NEXT PATIENT ---")

    def onAnalyzeButton(self):
        print("\033[H\033[J", end="")
        try:
            # Delete old tables, charts, and series to prevent RAM leaks
            for node in slicer.util.getNodesByClass("vtkMRMLTableNode"):
                if node.GetName().startswith("Table_"):
                    slicer.mrmlScene.RemoveNode(node)
            for node in slicer.util.getNodesByClass("vtkMRMLPlotChartNode"):
                if node.GetName().startswith("Chart_"):
                    slicer.mrmlScene.RemoveNode(node)
            for node in slicer.util.getNodesByClass("vtkMRMLPlotSeriesNode"):
                slicer.mrmlScene.RemoveNode(node)
            # --------------------------------------------

            self.resultsTextBox.setPlainText("Extracting 4D Time-Series Data...\nCalculating Kinetics...")
            slicer.app.processEvents() 
            
            # --- RUN THE MATH ENGINE ---
            all_data = self.logic.extract_dce_series()
            
            # We assume all segments share the same timeline
            time_data = list(all_data.values())[0]['time']
            
            self.resultsTextBox.setPlainText(f"Analysis Complete!\nAnalyzed {len(all_data)} discrete tumor regions.")
            slicer.app.processEvents()

            # --- THE FLOATING DASHBOARD ---
            self.dashboardWindow = qt.QDialog()
            self.dashboardWindow.setWindowTitle("Interactive DCE Kinetics Dashboard")
            self.dashboardWindow.resize(850, 650)
            self.dashboardWindow.setStyleSheet("background-color: #2c3e50; color: white; font-family: sans-serif;")
            
            dashLayout = qt.QVBoxLayout(self.dashboardWindow)
            
            title = qt.QLabel("Interactive Tumor ROI Analytics")
            title.setStyleSheet("font-size: 24px; font-weight: bold; margin: 10px;")
            title.setAlignment(qt.Qt.AlignCenter)
            dashLayout.addWidget(title)

            self.graphTabs = qt.QTabWidget()
            self.graphTabs.setStyleSheet("""
                QTabBar::tab { background: #34495e; padding: 8px 20px; font-size: 14px; min-width: 140px; } 
                QTabBar::tab:selected { background: #27ae60; font-weight: bold; }
            """)

            # --- NATIVE SLICER PLOT HELPER (Strictly Typed) ---
            def create_interactive_slicer_plot(title, x_label, y_label, series_configs, data_time):
                import vtk
                tableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", f"Table_{title}")
                
                arrX = vtk.vtkFloatArray()
                arrX.SetName("Time")
                for t in data_time:
                    arrX.InsertNextValue(float(t))
                tableNode.AddColumn(arrX)

                chartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode", f"Chart_{title}")
                chartNode.SetTitle(title)
                chartNode.SetXAxisTitle(x_label)
                chartNode.SetYAxisTitle(y_label)

                for config in series_configs:
                    arrY = vtk.vtkFloatArray()
                    arrY.SetName(config["name"])
                    for val in config["data"]:
                        arrY.InsertNextValue(float(val))
                    tableNode.AddColumn(arrY)

                    seriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode")
                    seriesNode.SetName(config["name"])
                    seriesNode.SetAndObserveTableNodeID(tableNode.GetID())
                    seriesNode.SetXColumnName("Time")
                    seriesNode.SetYColumnName(config["name"])
                    seriesNode.SetPlotType(slicer.vtkMRMLPlotSeriesNode.PlotTypeBar if config.get("type") == "Bar" else slicer.vtkMRMLPlotSeriesNode.PlotTypeScatter)
                    seriesNode.SetMarkerStyle(slicer.vtkMRMLPlotSeriesNode.MarkerStyleCircle)
                    
                    r, g, b = config["color"]
                    seriesNode.SetColor(r/255.0, g/255.0, b/255.0)
                    chartNode.AddAndObservePlotSeriesNodeID(seriesNode.GetID())

                plotWidget = slicer.qMRMLPlotWidget()
                plotWidget.setMRMLScene(slicer.mrmlScene)
                plotViewNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotViewNode")
                plotWidget.setMRMLPlotViewNode(plotViewNode)
                plotViewNode.SetPlotChartNodeID(chartNode.GetID())
                plotWidget.setMinimumHeight(350) 
                return plotWidget

            # --- DYNAMIC MULTI-LAYER GRAPH CONFIGURATION ---
            color_palette = [
                (46, 204, 113),  # Emerald Green
                (241, 196, 15),  # Sunflower Yellow
                (52, 152, 219),  # Peter River Blue
                (155, 89, 182),  # Amethyst Purple
                (231, 76, 60)    # Alizarin Red
            ]

            cfgMean, cfgSpread, cfgVar, cfgKin = [], [], [], []
            kinText = "CLINICAL KINETIC PARAMETERS:\n" + "="*48 + "\n"

            for idx, (seg_name, data) in enumerate(all_data.items()):
                # Pick a color from the palette based on the loop index
                c = color_palette[idx % len(color_palette)]
                dark_c = (max(0, c[0]-80), max(0, c[1]-80), max(0, c[2]-80)) # Darker shade for Min line

                # Compile data for all 4 tabs dynamically
                cfgMean.append({"name": f"{seg_name}", "data": data['mean'], "color": c, "type": "Line"})
                cfgSpread.append({"name": f"{seg_name} Max", "data": data['max'], "color": c, "type": "Line"})
                cfgSpread.append({"name": f"{seg_name} Min", "data": data['min'], "color": dark_c, "type": "Line"})
                cfgVar.append({"name": f"{seg_name}", "data": data['variance'], "color": c, "type": "Line"}) # Changed to line so bars don't overlap
                cfgKin.append({"name": f"{seg_name}", "data": data['enhancement_pct'], "color": c, "type": "Line"})
                
                kinText += f"""[{seg_name}]
                Tumor Size:               {data['voxel_count']} Voxels
                Time To Peak (TTP):       {data['ttp']}
                Peak Intensity:           {data['peak']} 
                Max Wash-in Slope:        +{data['max_slope']}
                Wash-out Slope:           {data['washout_slope']}
                Area Under Curve (AUC):   {data['auc']}
                {"-"*48}\n"""

            # TAB 1: Mean Intensity
            tabMean = qt.QWidget()
            layoutMean = qt.QVBoxLayout(tabMean)
            layoutMean.addWidget(create_interactive_slicer_plot("Mean Tumor Intensity Over Time", "Time Sequence", "Density", cfgMean, time_data))
            self.graphTabs.addTab(tabMean, "Mean Intensity")

            # TAB 2: Max/Min Spread
            tabSpread = qt.QWidget()
            layoutSpread = qt.QVBoxLayout(tabSpread)
            layoutSpread.addWidget(create_interactive_slicer_plot("Tumor Density Range", "Time Sequence", "Density", cfgSpread, time_data))
            self.graphTabs.addTab(tabSpread, "Max / Min Range")

            # TAB 3: Variance
            tabVar = qt.QWidget()
            layoutVar = qt.QVBoxLayout(tabVar)
            layoutVar.addWidget(create_interactive_slicer_plot("Tumor Heterogeneity", "Time Sequence", "Variance", cfgVar, time_data))
            self.graphTabs.addTab(tabVar, "Variance")

            # TAB 4: Clinical Kinetics Text & Graph
            tabKin = qt.QWidget()
            layoutKin = qt.QVBoxLayout(tabKin)
            
            # Make the text scrollable so it doesn't break the UI if you draw 10 segments
            scrollArea = qt.QScrollArea()
            lblKin = qt.QLabel(kinText)
            lblKin.setStyleSheet("font-family: monospace; font-size: 14px; background-color: #1e1e1e; padding: 15px; border-radius: 5px;")
            scrollArea.setWidget(lblKin)
            scrollArea.setWidgetResizable(True)
            scrollArea.setMaximumHeight(180) 
            layoutKin.addWidget(scrollArea)

            layoutKin.addWidget(create_interactive_slicer_plot("Relative Contrast Enhancement", "Time Sequence", "Enhancement %", cfgKin, time_data))
            self.graphTabs.addTab(tabKin, "Clinical Kinetics")

            dashLayout.addWidget(self.graphTabs)

            # --- THE NEW EXPORT BUTTON ---
            exportBtn = qt.QPushButton("Export CSV & Mask to Patient Folder")
            exportBtn.setStyleSheet("background-color: #2980b9; color: white; font-size: 14px; font-weight: bold; padding: 10px; margin-bottom: 5px;")
            
            # Pass the data array and the current folder path into the click event
            current_folder = self.inputDirSelector.currentPath
            exportBtn.clicked.connect(lambda: self.onExportClicked(all_data, current_folder))
            dashLayout.addWidget(exportBtn)

            # Close Button
            closeBtn = qt.QPushButton("Close Dashboard")
            closeBtn.setStyleSheet("background-color: #e74c3c; font-size: 14px; font-weight: bold; padding: 10px;")
            closeBtn.clicked.connect(lambda: self.dashboardWindow.hide())
            dashLayout.addWidget(closeBtn)

            self.dashboardWindow.show()
                
        except Exception as e:
            slicer.util.errorDisplay(f"Analysis failed: {e}")
    
    def onExportClicked(self, data, folder_path):
        import os
        try:
            # Clean the path to prevent Linux/Windows slash confusion
            clean_path = os.path.normpath(folder_path)
            
            # Call the noisy logic script
            self.logic.export_patient_data(data, clean_path)
            
            slicer.util.infoDisplay(
                f"Successfully saved to:\n{clean_path}/Analysis_Results\n\nFiles generated:\n- tumor_mask.seg.nrrd\n- tumor_mask.nii.gz\n- kinetics_report.csv", 
                windowTitle="Export Complete"
            )
        except Exception as e:
            # Force the error into the console so we can read it
            print(f"\nEXPORT FAILED: {str(e)}\n")
            slicer.util.errorDisplay(f"Failed to export data:\n{str(e)}")


class DCETumorAnalyzerLogic(ScriptedLoadableModuleLogic):
    def load_dce_data(self, dicom_dir):
        import slicer
        from DICOMLib import DICOMUtils
        
        db = slicer.dicomDatabase
        if not db or not db.isOpen:
            slicer.util.errorDisplay("Database not initialized. Click DCM -> Create.")
            return

        DICOMUtils.importDicom(dicom_dir)
        slicer.app.processEvents() 

        patientIds = db.patients()
        if patientIds:
            last_patient = patientIds[-1]
            studies = db.studiesForPatient(last_patient)
            if studies:
                series_uids = db.seriesForStudy(studies[-1])
                if series_uids:
                    DICOMUtils.loadSeriesByUID(list(series_uids))
                    slicer.util.resetSliceViews()

    def extract_dce_series(self):
        import slicer
        import vtk
        import numpy as np

        seg_node = slicer.mrmlScene.GetFirstNodeByName("My_Tumor_Drawings")
        if not seg_node or seg_node.GetSegmentation().GetNumberOfSegments() == 0:
            raise ValueError("No tumor drawn! Please paint the tumor first.")

        all_volumes = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        mri_volumes = []
        for node in all_volumes:
            name = node.GetName().lower()
            if "mask" not in name and "drawing" not in name:
                mri_volumes.append(node)

        if not mri_volumes:
            raise ValueError("Could not find the MRI time series in memory.")

        mri_volumes.sort(key=lambda n: n.GetName())

        # --- THE NEW MULTI-LAYER LOGIC ---
        segmentation = seg_node.GetSegmentation()
        segmentIDs = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIDs)
        
        multi_roi_data = {} # Our new master dictionary
        
        for i in range(segmentIDs.GetNumberOfValues()):
            seg_id = segmentIDs.GetValue(i)
            seg_name = segmentation.GetSegment(seg_id).GetName()
            
            # Extract the binary 1s and 0s specifically for THIS layer only
            mask_array = slicer.util.arrayFromSegmentBinaryLabelmap(seg_node, seg_id, mri_volumes[0])
            
            time_points = []
            means, maxs, mins, variances = [], [], [], []
            
            for idx, volume in enumerate(mri_volumes):
                slicer.app.processEvents()
                vol_array = slicer.util.arrayFromVolume(volume)
                tumor_pixels = vol_array[mask_array > 0]
                
                if len(tumor_pixels) > 0:
                    time_points.append(idx)
                    means.append(round(float(tumor_pixels.mean()), 2))
                    maxs.append(float(tumor_pixels.max()))
                    mins.append(float(tumor_pixels.min()))
                    variances.append(round(float(np.var(tumor_pixels)), 2))

            # Kinetics math for THIS layer
            baseline = means[0] if len(means) > 0 else 0
            peak_intensity = max(means) if len(means) > 0 else 0
            ttp_idx = means.index(peak_intensity) if len(means) > 0 else 0
            ttp = time_points[ttp_idx] if len(time_points) > 0 else 0
            auc = round(float(np.trapz(means, time_points)), 2) if len(time_points) > 1 else 0
            
            slopes = np.diff(means) / np.diff(time_points) if len(time_points) > 1 else [0]
            max_slope = round(float(max(slopes)), 2) if len(slopes) > 0 else 0
            
            washout_slope = 0
            if ttp_idx < len(means) - 1 and len(time_points) > 1:
                washout_slope = (means[-1] - peak_intensity) / (time_points[-1] - time_points[ttp_idx])
            washout_slope = round(float(washout_slope), 2)
            
            enhancement_pct = [round(((m - baseline) / baseline) * 100, 2) if baseline > 0 else 0 for m in means]

            # Save this layer's data into the master dictionary keyed by its name
            multi_roi_data[seg_name] = {
                "time": time_points,
                "mean": means,
                "max": maxs,
                "min": mins,
                "variance": variances,
                "voxel_count": len(tumor_pixels) if len(mri_volumes) > 0 else 0,
                "baseline": baseline,
                "peak": peak_intensity,
                "ttp": ttp,
                "auc": auc,
                "max_slope": max_slope,
                "washout_slope": washout_slope,
                "enhancement_pct": enhancement_pct
            }

        return multi_roi_data

    def export_patient_data(self, multi_roi_data, output_folder):
        import slicer
        import os
        import csv

        print(f"\n--- EXPORT PIPELINE STARTED ---")
        export_dir = os.path.normpath(os.path.join(output_folder, "Analysis_Results"))
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)

        seg_node = slicer.mrmlScene.GetFirstNodeByName("My_Tumor_Drawings")
        if not seg_node:
            raise ValueError("CRITICAL ERROR: Could not find 'My_Tumor_Drawings' in memory.")
            
        mask_path = os.path.join(export_dir, "tumor_mask.seg.nrrd")
        save_success = slicer.util.saveNode(seg_node, mask_path)
        if not save_success:
            raise IOError(f"CRITICAL ERROR: Slicer C++ engine refused to save the mask.")

        labelmap_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        reference_volume = None
        for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
            name = node.GetName().lower()
            if "mask" not in name and "drawing" not in name:
                reference_volume = node
                break
                
        if reference_volume:
            slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(seg_node, labelmap_node, reference_volume)
            nifti_path = os.path.join(export_dir, "tumor_mask.nii.gz")
            slicer.util.saveNode(labelmap_node, nifti_path)
            slicer.mrmlScene.RemoveNode(labelmap_node) # Clean up memory so Slicer doesn't slow down
            print(f"[SUCCESS] Saved NIfTI to: {nifti_path}")
        else:
            print("[WARNING] Could not find reference volume. NIfTI not saved.")


        csv_path = os.path.join(export_dir, "kinetics_report.csv")
        try:
            with open(csv_path, mode='w', newline='') as file:
                writer = csv.writer(file)
                
                # --- NEW: Loop through every drawn layer! ---
                for seg_name, data_dict in multi_roi_data.items():
                    writer.writerow([f"=== SEGMENT: {seg_name} ==="])
                    writer.writerow(["--- CLINICAL METRICS ---"])
                    writer.writerow(["Tumor Size (Voxels)", data_dict['voxel_count']])
                    writer.writerow(["Time To Peak (TTP)", data_dict['ttp']])
                    writer.writerow(["Peak Intensity", data_dict['peak']])
                    writer.writerow(["Max Wash-in Slope", data_dict['max_slope']])
                    writer.writerow(["Wash-out Slope", data_dict['washout_slope']])
                    writer.writerow(["Area Under Curve (AUC)", data_dict['auc']])
                    writer.writerow([])
                    
                    writer.writerow(["--- TIME SERIES DATA ---"])
                    writer.writerow(["Time Point", "Mean Density", "Max Density", "Min Density", "Variance", "Enhancement %"])
                    
                    for i in range(len(data_dict['time'])):
                        writer.writerow([
                            data_dict['time'][i], data_dict['mean'][i], data_dict['max'][i],
                            data_dict['min'][i], data_dict['variance'][i], data_dict['enhancement_pct'][i]
                        ])
                    writer.writerow([]) # Blank line between segments
                # --------------------------------------------
            print(f"[SUCCESS] Saved CSV to: {csv_path}")
        except Exception as e:
            raise IOError(f"CRITICAL ERROR: Python failed to write the CSV file. Details: {e}")

        print("--- EXPORT PIPELINE FINISHED ---\n")
        return True


class DCETumorAnalyzerTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_DCETumorAnalyzer1()

    def test_DCETumorAnalyzer1(self):
        self.delayDisplay("Starting the test")
        import SampleData
        registerSampleData()
        inputVolume = SampleData.downloadSample("DCETumorAnalyzer1")
        self.delayDisplay("Loaded test data set")
        
        self.delayDisplay("Test passed")