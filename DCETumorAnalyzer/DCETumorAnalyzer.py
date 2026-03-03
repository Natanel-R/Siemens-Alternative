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

    def onAnalyzeButton(self):
        print("\033[H\033[J", end="")
        try:
            self.resultsTextBox.setPlainText("Extracting 4D Time-Series Data...\nCalculating Kinetics...")
            slicer.app.processEvents() 
            
            # --- RUN THE MATH ENGINE ---
            data = self.logic.extract_dce_series()
            
            self.resultsTextBox.setPlainText(f"Analysis Complete!\nTumor Size: {data['voxel_count']} Voxels\nTime points analyzed: {len(data['time'])}")

            # --- THE FLOATING DASHBOARD ---
            self.dashboardWindow = qt.QDialog()
            self.dashboardWindow.setWindowTitle("DCE Kinetics & 1st Order Statistics")
            self.dashboardWindow.resize(800, 600)
            self.dashboardWindow.setStyleSheet("background-color: #2c3e50; color: white; font-family: sans-serif;")
            
            dashLayout = qt.QVBoxLayout(self.dashboardWindow)
            
            title = qt.QLabel("Tumor ROI Analytics")
            title.setStyleSheet("font-size: 24px; font-weight: bold; margin: 10px;")
            title.setAlignment(qt.Qt.AlignCenter)
            dashLayout.addWidget(title)

            self.graphTabs = qt.QTabWidget()
            self.graphTabs.setStyleSheet("""
                QTabBar::tab { background: #34495e; padding: 8px 20px; font-size: 14px; min-width: 140px; } 
                QTabBar::tab:selected { background: #27ae60; font-weight: bold; }
            """)

            # --- MATPLOTLIB SETUP (THE SAFE WAY) ---
            import matplotlib
            matplotlib.use('Agg') # Use the background rendering engine
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            
            # Helper: Create the dark theme
            def create_dark_figure():
                fig = Figure(figsize=(6, 4), dpi=100)
                fig.patch.set_facecolor('#2c3e50')
                ax = fig.add_subplot(111)
                ax.set_facecolor('#34495e')
                ax.tick_params(colors='white')
                ax.xaxis.label.set_color('white')
                ax.yaxis.label.set_color('white')
                ax.title.set_color('white')
                ax.grid(True, linestyle='--', alpha=0.5, color='#7f8c8d')
                for spine in ax.spines.values():
                    spine.set_edgecolor('#7f8c8d')
                return fig, ax

            # Helper: Convert Matplotlib Figure to Slicer UI Image
            def figure_to_widget(fig):
                import io
                
                # 1. Save the figure to an in-memory PNG file
                buf = io.BytesIO()
                fig.savefig(buf, format='png', facecolor=fig.get_facecolor(), bbox_inches='tight')
                buf.seek(0)
                
                # 2. Tell Slicer's Qt to load the PNG bytes directly
                pixmap = qt.QPixmap()
                pixmap.loadFromData(buf.getvalue())
                
                # 3. Put it in the UI
                label = qt.QLabel()
                label.setPixmap(pixmap)
                label.setAlignment(qt.Qt.AlignCenter)
                return label

            # TAB 1: Mean Intensity
            tabMean = qt.QWidget()
            layoutMean = qt.QVBoxLayout(tabMean)
            fig1, ax1 = create_dark_figure()
            ax1.plot(data['time'], data['mean'], marker='o', color='#2ecc71', linewidth=3, markersize=8)
            ax1.set_title('Mean Tumor Intensity Over Time (Wash-in Curve)')
            ax1.set_xlabel('MRI Time Sequence')
            ax1.set_ylabel('Mean Density')
            fig1.tight_layout()
            layoutMean.addWidget(figure_to_widget(fig1)) # Inject the converted image
            self.graphTabs.addTab(tabMean, "Mean Intensity")

            # TAB 2: Max/Min Spread
            tabSpread = qt.QWidget()
            layoutSpread = qt.QVBoxLayout(tabSpread)
            fig2, ax2 = create_dark_figure()
            ax2.plot(data['time'], data['max'], marker='^', color='#e74c3c', label='Max Density', linewidth=2)
            ax2.plot(data['time'], data['min'], marker='v', color='#3498db', label='Min Density', linewidth=2)
            ax2.fill_between(data['time'], data['min'], data['max'], color='#95a5a6', alpha=0.2)
            ax2.set_title('Tumor Density Range (Max vs Min)')
            ax2.set_xlabel('MRI Time Sequence')
            ax2.set_ylabel('Density Range')
            ax2.legend(facecolor='#34495e', edgecolor='white', labelcolor='white')
            fig2.tight_layout()
            layoutSpread.addWidget(figure_to_widget(fig2)) # Inject the converted image
            self.graphTabs.addTab(tabSpread, "Max / Min Range")

            # TAB 3: Variance
            tabVar = qt.QWidget()
            layoutVar = qt.QVBoxLayout(tabVar)
            fig3, ax3 = create_dark_figure()
            ax3.bar(data['time'], data['variance'], color='#9b59b6', width=0.4)
            ax3.set_title('Tumor Heterogeneity (Variance) Over Time')
            ax3.set_xlabel('MRI Time Sequence')
            ax3.set_ylabel('Variance')
            fig3.tight_layout()
            layoutVar.addWidget(figure_to_widget(fig3)) # Inject the converted image
            self.graphTabs.addTab(tabVar, "Variance")
            
            # TAB 4: Clinical Kinetics (The New Metrics)
            tabKin = qt.QWidget()
            layoutKin = qt.QVBoxLayout(tabKin)
            
            # 1. The Data Summary Text
            kinText = f"""
            CLINICAL KINETIC PARAMETERS:
            ------------------------------------------------
            Time To Peak (TTP):       {data['ttp']} (Time Unit)
            Peak Intensity:           {data['peak']} 
            Max Wash-in Slope:        +{data['max_slope']} / unit
            Wash-out Slope:           {data['washout_slope']} / unit
            Area Under Curve (AUC):   {data['auc']}
            """
            lblKin = qt.QLabel(kinText)
            lblKin.setStyleSheet("font-family: monospace; font-size: 14px; background-color: #1e1e1e; padding: 15px; border-radius: 5px;")
            layoutKin.addWidget(lblKin)

            # 2. The Relative Enhancement Graph
            fig4, ax4 = create_dark_figure()
            ax4.plot(data['time'], data['enhancement_pct'], marker='D', color='#f1c40f', linewidth=3, markersize=8)
            ax4.axhline(0, color='#7f8c8d', linestyle='--') # Add a zero-line
            ax4.set_title('Relative Contrast Enhancement (%)')
            ax4.set_xlabel('MRI Time Sequence')
            ax4.set_ylabel('Enhancement (%)')
            fig4.tight_layout()
            layoutKin.addWidget(figure_to_widget(fig4))
            
            self.graphTabs.addTab(tabKin, "Clinical Kinetics")

            # Add tabs to layout
            dashLayout.addWidget(self.graphTabs)

            # Close Button
            closeBtn = qt.QPushButton("Close Dashboard")
            closeBtn.setStyleSheet("background-color: #e74c3c; font-size: 14px; font-weight: bold; padding: 10px;")
            closeBtn.clicked.connect(lambda: self.dashboardWindow.hide())
            dashLayout.addWidget(closeBtn)

            self.dashboardWindow.show()
                
        except Exception as e:
            slicer.util.errorDisplay(f"Analysis failed: {e}")


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

        reference_volume = mri_volumes[0]
        labelmap_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(seg_node, labelmap_node, reference_volume)
        
        mask_array = slicer.util.arrayFromVolume(labelmap_node)

        time_points = []
        means = []
        maxs = []
        mins = []
        variances = []

        for idx, volume in enumerate(mri_volumes):
            vol_array = slicer.util.arrayFromVolume(volume)
            tumor_pixels = vol_array[mask_array > 0]
            
            if len(tumor_pixels) > 0:
                time_points.append(idx)
                means.append(round(float(tumor_pixels.mean()), 2))
                maxs.append(float(tumor_pixels.max()))
                mins.append(float(tumor_pixels.min()))
                variances.append(round(float(np.var(tumor_pixels)), 2))

        slicer.mrmlScene.RemoveNode(labelmap_node)

        # --- NEW KINETIC MATH (The Clinical Metrics) ---
        baseline = means[0] if len(means) > 0 else 0
        peak_intensity = max(means) if len(means) > 0 else 0
        ttp_idx = means.index(peak_intensity) if len(means) > 0 else 0
        ttp = time_points[ttp_idx] if len(time_points) > 0 else 0
        
        # 1. AUC (Area Under the Curve) via Trapezoidal Integration
        auc = round(float(np.trapz(means, time_points)), 2) if len(time_points) > 1 else 0

        # 2. Max Slope (Wash-in Rate)
        slopes = np.diff(means) / np.diff(time_points) if len(time_points) > 1 else [0]
        max_slope = round(float(max(slopes)), 2) if len(slopes) > 0 else 0
        
        # 3. Wash-out Slope (From Peak to End)
        if ttp_idx < len(means) - 1 and len(time_points) > 1:
            washout_slope = (means[-1] - peak_intensity) / (time_points[-1] - time_points[ttp_idx])
        else:
            washout_slope = 0
        washout_slope = round(float(washout_slope), 2)
        
        # 4. Relative Enhancement Percentage
        enhancement_pct = [round(((m - baseline) / baseline) * 100, 2) if baseline > 0 else 0 for m in means]
        # -----------------------------------------------

        return {
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