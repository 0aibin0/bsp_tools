# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_DisplayTools(object):
    def setupUi(self, DisplayTools):
        DisplayTools.setObjectName("DisplayTools")
        DisplayTools.resize(980, 960)

        self.centralwidget = QtWidgets.QWidget(DisplayTools)
        self.centralwidget.setObjectName("centralwidget")

        self.mainLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.mainLayout.setContentsMargins(6, 6, 6, 6)
        self.mainLayout.setSpacing(2)
        self.mainLayout.setObjectName("mainLayout")

        self.topBar = QtWidgets.QHBoxLayout()
        self.topBar.setObjectName("topBar")
        self.aboutBtn = QtWidgets.QPushButton(self.centralwidget)
        self.aboutBtn.setText("关于")
        self.aboutBtn.setMaximumWidth(50)
        self.aboutBtn.setMinimumHeight(24)
        self.aboutBtn.setObjectName("aboutBtn")
        self.topBar.addWidget(self.aboutBtn)
        self.changelogBtn = QtWidgets.QPushButton(self.centralwidget)
        self.changelogBtn.setText("更新日志")
        self.changelogBtn.setMinimumWidth(80)
        self.changelogBtn.setMinimumHeight(24)
        self.changelogBtn.setObjectName("changelogBtn")
        self.topBar.addWidget(self.changelogBtn)
        self.helpBtn = QtWidgets.QPushButton(self.centralwidget)
        self.helpBtn.setText("Help")
        self.helpBtn.setMaximumWidth(50)
        self.helpBtn.setMinimumHeight(24)
        self.helpBtn.setObjectName("helpBtn")
        self.topBar.addWidget(self.helpBtn)
        self.topBar.addStretch()
        self.mainLayout.addLayout(self.topBar)

        self.tabWidget = QtWidgets.QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName("tabWidget")
        self.tabWidget.setDocumentMode(True)
        self.mainLayout.addWidget(self.tabWidget)

        DisplayTools.setCentralWidget(self.centralwidget)

        self.statusbar = QtWidgets.QStatusBar(DisplayTools)
        self.statusbar.setObjectName("statusbar")
        DisplayTools.setStatusBar(self.statusbar)

        self.retranslateUi(DisplayTools)
        QtCore.QMetaObject.connectSlotsByName(DisplayTools)

    def retranslateUi(self, DisplayTools):
        _translate = QtCore.QCoreApplication.translate
        DisplayTools.setWindowTitle(_translate("DisplayTools", "DisplayTools"))
