import os
import matplotlib
if os.name == 'posix':
    matplotlib.use('Qt4Agg') # Force Mac users to use this backend
import tkinter as tk
from tkinter import ttk
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import __version__ as pltVersion
from matplotlib.patches import Rectangle
from astropy.io import fits
import warnings
import time
import csv
from spectrum import *
import pdb
from gui_utils import *

class Eyecheck(object):

    def __init__(self, specObj, options):
        
        # *** Store input variables ***
        
        self.specObj = specObj  # The Spectrum object created in the pyhammer script
        self.options = options  # The list of options input by the user in the pyhammer script

        # *** Define useful information ***
        
        self.specType  = ['O', 'B', 'A', 'F', 'G', 'K', 'M', 'L']
        self.subType   = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
        self.metalType = ['-2.0', '-1.5', '-1.0', '-0.5', '+0.0', '+0.5', '+1.0']
        self.templateDir = os.path.join(os.path.split(__file__)[0], 'resources', 'templates')

        # *** Read the infile ***
        
        self.inData = []
        with open(self.options['infile'], 'r') as file:
            for line in file:
                line = line.strip()
                if line.find(',') > 0: line = line.replace(',',' ')
                self.inData.append(' '.join(line.split()).rsplit(' ',1))
                self.inData[-1][0] = os.path.basename(self.inData[-1][0])
        self.inData = np.asarray(self.inData)

        # *** Read the outfile ***

        with open(self.options['outfile'], 'r') as file:
            reader = csv.reader(file)
            self.outData = np.asarray(list(reader)[1:]) # Ignore the header line
        
        # *** Define user's spectrum ***
        
        self.specIndex = 0      # The index in the inData where we should start from
        # Loop through the outData and see if some classification has occured already
        for i in range(len(self.outData)):
            # If classification by the user has already occured for the
            # current spectrum, then move to the next one.
            if self.outData[self.specIndex,4] != 'nan' or self.outData[self.specIndex,5] != 'nan':
                self.specIndex += 1
            else:
                # Break out if we can get to a spectrum that hasn't been
                # classified by the user yet
                break
        # If the outfile already has eyecheck results, ask if they want
        # to start where they left off
        if self.specIndex != 0:
            # If every outfile spectra already has an eyecheck result
            # they've classified everything and ask them if they want
            # to start over instead.
            if self.specIndex == i+1:
                modal = ModalWindow('Every spectrum in the output file already has\nan eyecheck result. Do you want to start over?')
                if modal.choice == 'yes':
                    self.specIndex = 0
                else:
                    return
            else:
                modal = ModalWindow('The output file already has eyecheck results. The\n'
                                    'eyecheck will start with the next unclassified\n'
                                    'spectrum. Do you want to start over instead?')
                if modal.choice == 'yes':
                    self.specIndex = 0
        # Now use the Spectrum object to read in the user's appropriate starting spectrum
        fname = self.outData[self.specIndex,0]
        ftype = np.extract(self.inData[:,0] == os.path.basename(fname), self.inData[:,1])[0]
        self.specObj.readFile(self.options['spectraPath']+fname, ftype) # Ignore returned values
        self.specObj.normalizeFlux()
        
        # *** Define GUI variables ***
        
        self.root = tk.Tk()             # Create the root GUI window
        # Define String and Int variables to keep track of widget states
        self.spectrumEntry = tk.StringVar(value = os.path.basename(self.outData[self.specIndex,0]))
        self.specState  = tk.IntVar(value = self.specType.index(self.outData[self.specIndex,2][0]))
        self.subState   = tk.IntVar(value = int(self.outData[self.specIndex,2][1]))
        self.metalState = tk.IntVar(value = self.metalType.index(self.outData[self.specIndex,3]))
        self.subButtons = []            # We keep track of these radio buttons so
        self.metalButtons = []          # they can be enabled and disabled if need be
        self.smoothState = tk.BooleanVar(value = False)
        self.lockSmooth = tk.BooleanVar(value = False)
        self.showTemplateError = tk.BooleanVar(value = True)
        self.removeSdssSpikeState = tk.BooleanVar(value = False)

        # *** Define figure variables ***
        
        plt.ion()                       # Turn on plot interactivity
        plt.style.use('ggplot')         # Makes the plot look nice
        self.full_xlim = None           # +--
        self.full_ylim = None           # | Store these to keep track
        self.zoomed_xlim = None         # | of zoom states on the plot
        self.zoomed_ylim = None         # |
        self.zoomed = False             # +--
        self.updatePlot()               # Create the plot
        # Other variables
        self.pPressNum = 0
        self.pPressTime = 0

        # *** Initialize the GUI
        
        self.setupGUI()                 # Call the method for setting up the GUI layout        
        self.root.mainloop()            # Run the GUI
        
    ###
    # Setup/Close Methods
    #

    def areYouSure(self):
        """
        Description:
            In some cases, if the user wants to quit, we should ask if they're
            sure they want to quit before moving on to the _exit function.
        """
        modal = ModalWindow('Are you sure you want to quit?', parent = self.root, title = 'Quit')
        self.root.wait_window(modal.modalWindow)
        if modal.choice == 'yes':
            self._exit()
    
    def _exit(self):
        """
        Description:
            This method is called anytime the user wants to quit the program.
            It will be called if the "X" out of the GUI window, if they choose
            quit from the menu, or if they finish classifying and say they're
            done. This function will first write the self.outData variable
            contents to their outfile, then clean up the GUI and matplotlib
            window.
        """
        # Write the outData to the output file
        with open(self.options['outfile'], 'w') as outfile:
            outfile.write('#Filename,Radial Velocity (km/s),Guessed Spectral Type,Guessed [Fe/H],User Spectral Type,User [Fe/H]\n')
            for i, spectra in enumerate(self.outData):
                for j, col in enumerate(spectra):
                    outfile.write(col)
                    if j < 5: outfile.write(',')
                if i < len(self.outData)-1: outfile.write('\n')
        # Close down the GUI and plot window
        self.root.destroy()
        plt.close('all')

    def setupGUI(self):
        """
        Description:
            This handles setting up all the widgets on the main GUI window and
            defining the initial state of the GUI. 
        """
        
        # *** Set root window properties ***
        
        self.root.title('PyHammer Eyecheck')
        if os.name == 'nt': self.root.iconbitmap(os.path.join(os.path.split(__file__)[0],'resources','sun.ico'))
        self.root.resizable(False, False)
        self.root.geometry('+100+100')
        # Set the close protocol to call this class' personal exit function
        self.root.protocol('WM_DELETE_WINDOW', self.areYouSure)

        # *** Define menubar ***
        
        menubar = tk.Menu() # Create the overall menubar

        # Define the options menu
        optionsMenu = tk.Menu(menubar, tearoff = 1)
        optionsMenu.add_checkbutton(label = 'Show Template Error', variable = self.showTemplateError, command = self.updatePlot)
        optionsMenu.add_checkbutton(label = 'Smooth Spectrum', variable = self.smoothState, command = self.callback_smooth)
        optionsMenu.add_checkbutton(label = 'Lock Smooth State', variable = self.lockSmooth)
        optionsMenu.add_checkbutton(label = 'Remove SDSS Stitch Spike', variable = self.removeSdssSpikeState, command = self.updatePlot)
        optionsMenu.add_separator()
        optionsMenu.add_command(label = 'Quit', command = self.areYouSure)

        # Define the about menu
        helpMenu = tk.Menu(menubar, tearoff = 0)
        helpMenu.add_command(label = 'Help', command = self.callback_help)
        helpMenu.add_command(label = 'About', command = self.callback_about)

        # Put all menus together
        menubar.add_cascade(label = 'Options', menu = optionsMenu)
        menubar.add_cascade(label = 'Help', menu = helpMenu)
        self.root.config(menu = menubar)
        
        # *** Define labels ***
        
        for i, name in enumerate(['Spectrum', 'Type', 'Subtype', '[Fe/H]', 'Switch Type', 'Switch [Fe/H]', 'Spectrum Choices']):
            ttk.Label(self.root, text = name).grid(row = i, column = 0, columnspan = 1+(i>3),
                                                   stick = 'e', pady = (10*(i==4),10*(i==0)))

        # *** Define entry box ***

        # This defines the entry box and relevant widgets for indicating the spectrum
        ttk.Entry(self.root, textvariable = self.spectrumEntry).grid(row = 0, column = 1, columnspan = 9, pady = (0,10), sticky = 'nesw')
        but = ttk.Button(self.root, text = 'Go', width = 3, command = self.jumpToSpectrum)
        but.grid(row = 0, column = 10, pady = (0,10))
        ToolTip(but, 'Enter a new spectrum file name in the entry box\nand hit Go to skip directly to that spectrum.')

        # *** Define radio buttons ***
        
        # First the radio buttons for the spectral type
        for ind, spec in enumerate(self.specType):
            temp = ttk.Radiobutton(self.root, text = spec, variable = self.specState, value = ind,
                                   command = lambda: self.callback_specRadioChange(True))
            temp.grid(row = 1, column = ind+1, sticky = 'nesw')
            
        # Now the sub spectral type radio buttons
        for ind, sub in enumerate(self.subType):
            self.subButtons.append(ttk.Radiobutton(self.root, text = sub, variable = self.subState, value = ind,
                                                   command = lambda: self.callback_subRadioChange(True)))
            self.subButtons[-1].grid(row = 2, column = ind+1, sticky = 'nesw')
            
        # Finally the radio buttons for the metallicities
        for ind, metal in enumerate(self.metalType):
            self.metalButtons.append(ttk.Radiobutton(self.root, text = metal, variable = self.metalState, value = ind,
                                                     command = lambda: self.callback_metalRadioChange(True)))
            self.metalButtons[-1].grid(row = 3, column = ind+1, sticky = 'nesw')
            
        # *** Define buttons ***
        
        # These will be the buttons for interacting with the data (e.g., smooth it, next, back)
        ttk.Button(self.root, text = 'Earlier', command = self.callback_earlier).grid(row = 4, column = 2, columnspan = 4, sticky = 'nesw', pady = (10,0))
        ttk.Button(self.root, text = 'Later', command = self.callback_later).grid(row = 4, column = 6, columnspan = 4, sticky = 'nesw', pady = (10,0))
        ttk.Button(self.root, text = 'Lower', command = self.callback_lower).grid(row = 5, column = 2, columnspan = 4, sticky = 'nesw')
        ttk.Button(self.root, text = 'Higher', command = self.callback_higher).grid(row = 5, column = 6, columnspan = 4, sticky = 'nesw')
        ttk.Button(self.root, text = 'Odd', underline = 0, command = self.callback_odd).grid(row = 6, column = 2, columnspan = 2, sticky = 'nesw')
        ttk.Button(self.root, text = 'Bad', underline = 0, command = self.callback_bad).grid(row = 6, column = 4, columnspan = 2, sticky = 'nesw')
        ttk.Button(self.root, text = 'Back', underline = 3, command = self.callback_back).grid(row = 6, column = 6, columnspan = 2, sticky = 'nesw')
        ttk.Button(self.root, text = 'Next', command = self.callback_next).grid(row = 6, column = 8, columnspan = 2, sticky = 'nesw')

        # *** Set key bindings ***
        
        self.root.bind('<Control-o>', lambda event: self.callback_odd())
        self.root.bind('<Control-b>', lambda event: self.callback_bad())
        self.root.bind('<Control-s>', lambda event: self.callback_smooth(toggle = True))
        self.root.bind('<Control-e>', lambda event: self.showTemplateError.set(not self.showTemplateError.get()))
        self.root.bind('<Control-e>', lambda event: self.updatePlot(), add = '+')
        self.root.bind('<Control-l>', lambda event: self.lockSmooth.set(not self.lockSmooth.get()))
        self.root.bind('<Control-r>', lambda event: self.removeSdssSpikeState.set(not self.removeSdssSpikeState.get()))
        self.root.bind('<Control-r>', lambda event: self.updatePlot(), add = '+')
        self.root.bind('<Return>', lambda event: self.callback_next())
        self.root.bind('<Control-k>', lambda event: self.callback_back())
        self.root.bind('<Left>', lambda event: self.callback_earlier())
        self.root.bind('<Right>', lambda event: self.callback_later())
        self.root.bind('<Down>', lambda event: self.callback_lower())
        self.root.bind('<Up>', lambda event: self.callback_higher())
        self.root.bind('<Control-p>', lambda event: self.callback_hammer_time())

        # Force the GUI to appear as a top level window, on top of all other windows
        self.root.lift()
        self.root.call('wm', 'attributes', '.', '-topmost', True)
        self.root.after_idle(self.root.call, 'wm', 'attributes', '.', '-topmost', False)

    def updatePlot(self):
        """
        Description:
            This is the method which handles all the plotting on the matplotlib
            window. It will plot the template (if it exists), the user's spectrum
            and do things like control the zoom level on the plot.
        """
        
        # Before updating the plot, check the current axis limits. If they're
        # set to the full limit values, then the plot wasn't zoomed in on when
        # they moved to a new plot. If the limits are different, they've zoomed
        # in and we should store the current plot limits so we can set them
        # to these limits at the end.
        if self.full_xlim is not None and self.full_ylim is not None:
            if (self.full_xlim == plt.gca().get_xlim() and
                self.full_ylim == plt.gca().get_ylim()):
                self.zoomed = False
            else:
                self.zoomed = True
                self.zoomed_xlim = plt.gca().get_xlim()
                self.zoomed_ylim = plt.gca().get_ylim()
        

        # *** Define Initial Figure ***
        
        fig = plt.figure('Pyhammer Spectrum Matching', figsize = (12,6))
        plt.cla()   # Clear the plot
        if plt.get_current_fig_manager().toolbar._active != 'ZOOM':
            # Make it so the zoom button is selected by default
            plt.get_current_fig_manager().toolbar.zoom()

        # *** Plot the template ***

        # Determine which, if any, template file to load
        templateFile = self.getTemplateFile()
        
        if templateFile is not None:
            # Load in template data
            with warnings.catch_warnings():
                # Ignore a very particular warning from some versions of astropy.io.fits
                # that is a known bug and causes no problems with loading fits data.
                warnings.filterwarnings('ignore', message = 'Could not find appropriate MS Visual C Runtime ')
                hdulist = fits.open(templateFile)
            lam = np.power(10,hdulist[1].data['loglam'][::10])
            flux = hdulist[1].data['flux'][::10]
            std = hdulist[1].data['std'][::10]

            # The templates are all normalized to 8000 Angstroms. The loaded spectrum
            # are normalized to this by default as well, but if they're not defined at 8000 Angstroms,
            # it is normalized to a different value that the template needs to be normalized to
            if self.specObj.normWavelength != 8000:
                flux = Spectrum.normalize(lam, self.specObj.normWavelength, flux)

            # Plot template error bars and spectrum line
            plt.plot(lam, flux, '-k', label = 'Template')
            if self.showTemplateError.get():    # Only plot template error if option is selected to do so
                plt.fill_between(lam, flux+std, flux-std, color = 'b', edgecolor = 'None', alpha = 0.1, label = 'Template RMS')
            # Determine and format the template name for the title, from the filename
            templateName = os.path.basename(os.path.splitext(templateFile)[0])
            if '_' in templateName:
                ii = templateName.find('_')+1 # Index of first underscore, before metallicity
                templateName = templateName[:ii] + '[Fe/H] = ' + templateName[ii:]
                templateName = templateName.replace('_',',\;')
        else:
            # No template exists, plot nothing
            templateName = 'Not\;Available'
            
        # *** Plot the user's data ***

        # Get the flux and fix it as the user requested
        if self.smoothState.get() == False:
            flux = self.specObj.flux
        else:
            flux = self.specObj.smoothFlux
            
        if self.removeSdssSpikeState.get() == True:
            flux = Spectrum.removeSdssStitchSpike(self.specObj.wavelength, flux)

        # Plot it all up and define the title name
        plt.plot(self.specObj.wavelength, flux, '-r', alpha = 0.75, label = 'Your Spectrum')
        spectraName = os.path.basename(os.path.splitext(self.outData[self.specIndex,0])[0])
        

        # *** Set Plot Labels ***
        
        plt.xlabel(r'$\mathrm{Wavelength\;[\AA]}$', fontsize = 16)
        plt.ylabel(r'$\mathrm{Normalized\;Flux}$', fontsize = 16)
        plt.title(r'$\mathrm{Template:\;' + templateName + '}$\n$\mathrm{Spectrum:\;' + spectraName.replace('_','\_') + '}$', fontsize = 16)

        # *** Set Legend Settings ***

        handles, labels = plt.gca().get_legend_handles_labels()
        # In matplotlib versions before 1.5, the fill_between plot command above
        # does not appear in the legend. In those cases, we will fake it out by
        # putting in a fake legend entry to match the fill_between plot.
        if pltVersion < '1.5' and self.showTemplateError.get() and templateFile is not None:
            labels.append('Template RMS')
            handles.append(Rectangle((0,0),0,0, color = 'b', ec = 'None', alpha = 0.1))
        labels, handles = zip(*sorted(zip(labels, handles), key=lambda t: t[0]))
        leg = plt.legend(handles, labels, loc = 0)
        leg.get_frame().set_alpha(0)
        # Set legend text colors to match plot line colors
        if templateFile is not None:
            # Don't adjust the template error if it wasn't plotted
            if self.showTemplateError.get():
                plt.setp(leg.get_texts()[1], color = 'b', alpha = 0.5)  # Adjust template error, alpha is higher to make more readable
                plt.setp(leg.get_texts()[2], color = 'r', alpha = 0.75) # Adjust spectrum label
            else:
                plt.setp(leg.get_texts()[1], color = 'r', alpha = 0.75) # Adjust spectrum table
        else:
            plt.setp(leg.get_texts()[0], color = 'r', alpha = 0.6)

        # *** Set Plot Spacing ***
        
        plt.subplots_adjust(left = 0.075, right = 0.975, top = 0.9, bottom = 0.15)
        
        # *** Set Plot Limits ***

        plt.xlim([3000,11000])                  # Set x axis limits to constant value
        fig.canvas.toolbar.update()             # Clears out view stack
        self.full_xlim = plt.gca().get_xlim()   # Pull out default, current x-axis limit
        self.full_ylim = plt.gca().get_ylim()   # Pull out default, current y-axis limit
        fig.canvas.toolbar.push_current()       # Push the current full zoom level to the view stack
        if self.zoomed:                         # If the previous plot was zoomed in, we should zoom this too
            plt.xlim(self.zoomed_xlim)          # Set to the previous plot's zoom level
            plt.ylim(self.zoomed_ylim)          # Set to the previous plot's zoom level
            fig.canvas.toolbar.push_current()   # Push the current, zoomed level to the view stack so it shows up first

        # *** Draw the Plot ***
    
        plt.draw()
        

    ##
    # Menu Item Callbacks
    #
    
    def callback_help(self):
        mainStr = (
            'Welcome to the main GUI for spectral typing your spectra.\n\n'
            'Each spectra in your spectra list file will be loaded in '
            'sequence and shown on top of the template it was matched '
            'to. From here, fine tune the spectral type by comparing '
            'your spectrum to the templates and choose "Next" when '
            "you've landed on the correct choice. Continue through each "
            'spectrum until finished.')
        buttonStr = (
            'Upon opening the Eyecheck program, the first spectrum in your '
            'list will be loaded and displayed on top of the template determined '
            'by the spectral type guesser.\n\n'
            'Use the "Earlier" and "Later" buttons to change the spectrum '
            'templates. Note that not all templates exist for all spectral '
            'types. This program specifically disallows choosing K8 and K9 '
            'spectral types as well.\n\n'
            'The "Higher" and "Lower" buttons change the metallicity. Again, '
            'not all metallicities exist as templates.\n\n'
            'The "Odd" button allows you to mark a spectrum as something other '
            'than a standard classification, such as a white dwarf or galaxy.\n\n'
            'The "Bad" button simply marks the spectrum as BAD in the output '
            'file, indicating it is not able to be classified.\n\n'
            'You can cycle between your spectra using the "Back" and "Next" buttons. '
            'Note that hitting "Next" will save the currently selected state as '
            'the classification for that spectra.')
        keyStr = (
            'The following keys are mapped to specific actions.\n\n'
            '<Left>\tEarlier spectral type button\n'
            '<Right>\tLater spectral type button\n'
            '<Up>\tHigher metallicity button\n'
            '<Down>\tLower metallicity button\n'
            '<Enter>\tAccept spectral classification\n'
            '<Ctrl-K>\tMove to previous spectrum\n'
            '<Ctrl-O>\tClassify spectrum as odd\n'
            '<Ctrl-B>\tClassify spectrum as bad\n'
            '<Ctrl-E>\tToggle the template error\n'
            '<Ctrl-S>\tSmooth/Unsmooth the spectrum\n'
            '<Ctrl-L>\tLock the smooth state between spectra\n'
            '<Ctrl-R>\tToggle removing the stiching spike in SDSS spectra\n'
            '<Ctrl-P>')
        tipStr = (
            'The following are a set of tips for useful features of the '
            'program.\n\n'
            'Any zoom applied to the plot is held constant between switching '
            'templates. This makes it easy to compare templates around specific '
            'features or spectral lines. Hit the home button on the plot '
            'to return to the original zoom level.\n\n'
            'The entry field on the GUI will display the currently plotted '
            'spectrum. You can choose to enter one of the spectra in your list'
            'and hit the "Go" button to automatically jump to that spectrum.\n\n'
            'The smooth menu option will allow you to smooth or unsmooth '
            'your spectra in the event that it is noisy. This simply applies '
            'a boxcar convolution across your spectrum, leaving the edges unsmoothed.\n\n'
            'By default, every new, loaded spectrum will be unsmoothed and '
            'the smooth button state reset. You can choose to keep the smooth '
            'button state between loading spectrum by selecting the menu option '
            '"Lock Smooth State".\n\n'
            'In SDSS spectra, there is a spike that occurs between 5569 and 5588'
            'angstroms caused by stitching together the results from both detectors.'
            'You can choose to artificially remove this spike for easier viewing by'
            'selecting the "Remove SDSS Stitch Spike" from the Options menu.\n\n'
            'Some keys may need to be hit rapidly.')
        contactStr = (
            'Aurora Kesseli\n'
            'aurorak@bu.edu')
        InfoWindow(('Main',    mainStr),
                   ('Buttons', buttonStr),
                   ('Keys',    keyStr),
                   ('Tips',    tipStr),
                   ('Contact', contactStr), parent = self.root, title = 'PyHammer Help', height = 8)

    def callback_about(self):
        aboutStr = (
            'This project was developed by a select group of graduate students '
            'at the Department of Astronomy at Boston University. The project '
            'was lead by Aurora Kesseli with development help and advice provided '
            'by Andrew West, Mark Veyette, Brandon Harrison, and Dan Feldman. '
            'Contributions were further provided by Dylan Morgan and Chris Theissan.\n\n'
            'See the acompanying paper Kesseli et al. (2016) for further details.')
        InfoWindow(aboutStr, parent = self.root, title = 'PyHammer About')

    ##
    # Button and Key Press Callbacks
    #
    
    def callback_odd(self):
        # Open an OptionWindow object and wait for a user response
        choice = OptionWindow(['Wd', 'Wdm', 'Carbon', 'Gal', 'Unknown'], parent = self.root, title = 'PyHammer', instruction = 'Pick an odd type')
        self.root.wait_window(choice.optionWindow)
        if choice.name is not None:
            # Store the user's response in the outData
            self.outData[self.specIndex,4] = choice.name
            self.outData[self.specIndex,5] = 'nan'
            # Move to the next spectra
            self.moveToNextSpectrum()
        
    def callback_bad(self):
        # Store BAD as the user's choices
        self.outData[self.specIndex,4] = 'BAD'
        self.outData[self.specIndex,5] = 'BAD'
        # Move to the next spectra
        self.moveToNextSpectrum()
        
    def callback_smooth(self, toggle = False):
        if toggle:
            self.smoothState.set(not self.smoothState.get())
        # Update the plot now
        self.updatePlot()
        
    def callback_next(self):
        # Store the choice for the current spectra
        self.outData[self.specIndex,4] = self.specType[self.specState.get()] + str(self.subState.get())
        self.outData[self.specIndex,5] = self.metalType[self.metalState.get()]
        # Move to the next spectra
        self.moveToNextSpectrum()
        
    def callback_back(self):
        self.moveToPreviousSpectrum()
    
    def callback_earlier(self):
        curSub  = self.subState.get()
        curSpec = self.specState.get()
        # If user hasn't selected "O" spectral type and they're
        # currently selected zero sub type, we need to loop around
        # to the previous spectral type
        if curSpec != 0 and curSub == 0:
            # Set the sub spectral type, skipping over K8 and K9
            # since they don't exist.
            self.subState.set(7 if curSpec == 6 else 9)
            # Decrease the spectral type
            self.specState.set(curSpec - 1)
        else:
            # Just decrease sub spectral type
            self.subState.set(curSub - 1)

        # Call the spectral and sub spectral type radio
        # button change callbacks as if the user changed
        # the buttons themselves
        self.callback_specRadioChange(True)
        self.callback_subRadioChange(False)

    def callback_later(self):
        curSub  = self.subState.get()
        curSpec = self.specState.get()
        # If the user hasn't selected "L" spectral type and
        # they're currently selecting "9" spectral sub type
        # (or 7 if spec type is "K"), we need to loop around
        # to the next spectral type
        if curSpec != 7 and (curSub == 9 or (curSpec == 5 and curSub == 7)):
            self.specState.set(curSpec + 1)
            self.subState.set(0)
        else:
            # Just increase the sub spectral type
            self.subState.set(curSub + 1)

        # Call the spectral and sub spectral type radio
        # button change callbacks as if the user changed
        # the buttons themselves.
        self.callback_specRadioChange(True)
        self.callback_subRadioChange(False)

    def callback_higher(self):
        curMetal = self.metalState.get()
        # If the user isn't at the max metallicity option,
        # then increase the metallicity
        if curMetal != 6:
            self.metalState.set(curMetal + 1)
        # Call the metallicity radio button change callback
        # as if the user changed the button themselves.
        self.callback_metalRadioChange(True)

    def callback_lower(self):
        curMetal = self.metalState.get()
        # If the user isn't at the min mellaticity option,
        # then decrease the metallicity
        if curMetal != 0:
            self.metalState.set(curMetal - 1)
        # Call the metallicity radio button change callback
        # as if the user changed the button themselves.
        self.callback_metalRadioChange(True)

    def callback_hammer_time(self):
        timeCalled = time.time()
        if self.pPressTime == 0 or timeCalled - self.pPressTime > 1.5:
            # Reset
            self.pPressTime = timeCalled
            self.pPressNum = 1
            return
        else:
            self.pPressNum += 1

        if self.pPressNum == 5:
            chrList = [(10,1),(32,18),(46,1),(39,1),(47,1),(32,26),(10,1),(32,1),(42,1),(32,3),(39,1),(42,1),(32,10),(47,1),(32,1),(40,1),(95,11),
                       (46,1),(45,12),(46,1),(32,2),(10,1),(32,9),(42,1),(32,7),(91,1),(32,1),(93,1),(95,11),(124,1),(47,2),(80,1),(121,1),(72,1),
                       (97,1),(109,2),(101,1),(114,1),(47,2),(124,1),(32,2),(10,1),(32,14),(42,1),(32,2),(41,1),(32,1),(40,1),(32,11),(39,1),(45,12),
                       (39,1),(32,2),(10,1),(32,17),(39,1),(45,1),(39,1),(32,1),(42,1),(32,25),(10,1),(32,13),(42,1),(32,33),(10,1),(32,19),(42,1),(32,27)]
            InfoWindow(''.join([chr(c[0])*c[1] for c in chrList]), parent = self.root, height = 9, fontFamily = 'Courier')
        

    ##
    # Radiobutton Selection Change Callbacks
    #

    def callback_specRadioChange(self, callUpdatePlot):
        # If the spectral type radio button has changed,
        # check to see if the user switched to a "K" type.
        # If they have, turn off the option to pick K8 and K9
        # Since those don't exist. Otherwise, just turn those
        # sub spectral type buttons on.
        if self.specState.get() == 5:
            self.subButtons[-1].configure(state = 'disabled')
            self.subButtons[-2].configure(state = 'disabled')
            if self.subState.get() == 8 or self.subState.get() == 9:
                self.subState.set(7)
        else:
            self.subButtons[-1].configure(state = 'normal')
            self.subButtons[-2].configure(state = 'normal')
            
        if callUpdatePlot: self.updatePlot()

    def callback_subRadioChange(self, callUpdatePlot):
        if callUpdatePlot: self.updatePlot()

    def callback_metalRadioChange(self, callUpdatePlot):
        if callUpdatePlot: self.updatePlot()

    ##
    # Utility Methods
    #

    def moveToNextSpectrum(self):
        """
        Description:
            This method handles moving to the next spectrum. All it really
            does is determines if the user is at the end of the list of
            spectrum, and, if so, asks if they're done. If they aren't at
            the end, it moves to the next spectrum (by incrementing self.specIndex)
            and calling self.getUserSpectrum.
        """
        if self.specIndex+1 >= len(self.outData):
            self.root.bell()
            modal = ModalWindow("You've classified all the spectra. Are you finished?", parent = self.root)
            self.root.wait_window(modal.modalWindow)
            if modal.choice == 'yes':
                self._exit()
        else:
            self.specIndex += 1
            self.getUserSpectrum()

    def moveToPreviousSpectrum(self):
        """
        Description:
            This method handles moving to the previous spectrum. It will simply
            decrement the self.specIndex variable if they're not already on
            the first index and call self.getUserSpectrum.
        """
        if self.specIndex > 0:
            self.specIndex -= 1
            self.getUserSpectrum()

    def jumpToSpectrum(self):
        """
        Description:
            This method handles moving to a different spectrum in the list which
            may or may not be before or after the current spectrum. This is handled
            by looking for a spectrum in the inData list which matches the spectrum
            in the Entry field in the GUI. If a match is found, that spectrum is
            loaded, otherwise they're informed that spectrum could not be found.
        """
        spectrumFound = False
        # Get the user's input spectrum name and make sure it has an extension
        userInput = os.path.basename(self.spectrumEntry.get())
        if userInput.find('.') == -1:
            message = 'Make sure to provide a file extension in your name.'
            InfoWindow(message, parent = self.root, title = 'PyHammer Error')
            return
        # Scan through the outData file and try to find a matching spectrum
        for i, spectrum in enumerate(self.outData):
            if userInput == os.path.basename(spectrum[0]):
                self.specIndex = i
                spectrumFound = True
                break
        # If one wasn't found, inform the user of a problem
        if not spectrumFound:
            message = ('The spectrum you input could not be matched '
                       'to any of the spectrum in your output file '
                       'list. Check your input and try again.')
            InfoWindow(message, parent = self.root, title = 'PyHammer Error')
        else:
            # If a match was found, load that spectrum
            self.getUserSpectrum()

    def getUserSpectrum(self):
        """
        Description:
            This handles loading a new spectrum based on the self.specIndex variable
            and updates the GUI and plot window accordingly.
        """
        # Read in the next spectrum file indicated by self.specIndex
        fname = self.outData[self.specIndex,0]
        ftype = np.extract(self.inData[:,0] == os.path.basename(fname), self.inData[:,1])[0]
        self.specObj.readFile(self.options['spectraPath']+fname, ftype) # Ignore returned values
        self.specObj.normalizeFlux()
        # Set the spectrum entry field to the new spectrum name
        self.spectrumEntry.set(os.path.basename(self.outData[self.specIndex,0]))
        # Set the radio button selections to the new spectrum's guessed classifcation
        self.specState.set(self.specType.index(self.outData[self.specIndex,2][0]))
        self.subState.set(int(self.outData[self.specIndex,2][1]))
        self.metalState.set(self.metalType.index(self.outData[self.specIndex,3]))
        # Reset the indicator for whether the plot is zoomed. It should only stay zoomed
        # between loading templates, not between switching spectra.
        self.full_xlim = None
        self.full_ylim = None
        self.zoomed = False
        # Reset the smooth state to be unsmoothed, unless the user chose to lock the state
        if not self.lockSmooth.get():
            self.smoothState.set(False)
        # Update the plot
        self.updatePlot()

    def getTemplateFile(self, specState = None, subState = None, metalState = None):
        """
        Description:
            This will determine the filename for the template which matches the
            current template selection. Either that selection will come from
            whichever radio buttons are selected, or else from input to this
            function. This will search for filenames matching a specific format.
            The first attempt will be to look for a filename of the format
            "SS_+M.M_Dwarf.fits", where the SS is the spectral type and subtype
            and +/-M.M is the [Fe/H] metallicity. The next next format it will
            try (if the first doesn't exist) is "SS_+M.M.fits". After that it
            will try "SS.fits".
        """
        # If values weren't passed in for certain states, assume we should
        # use what is chosen on the GUI
        if specState is None: specState = self.specState.get()
        if subState is None: subState = self.subState.get()
        if metalState is None: metalState = self.metalState.get()

        # Try using the full name
        filename = self.specType[specState] + str(subState) + '_' + self.metalType[metalState] + '_Dwarf'

        fullPath = os.path.join(self.templateDir, filename + '.fits')

        if os.path.isfile(fullPath):
            return fullPath

        # Try using only the spectra and metallicity in the name
        filename = filename[:7]

        fullPath = os.path.join(self.templateDir, filename + '.fits')

        if os.path.isfile(fullPath):
            return fullPath
        
        # Try to use just the spectral type
        filename = filename[:2]

        fullPath = os.path.join(self.templateDir, filename + '.fits')
        
        if os.path.isfile(fullPath):
            return fullPath

        # Return None if file could not be found
        return None
