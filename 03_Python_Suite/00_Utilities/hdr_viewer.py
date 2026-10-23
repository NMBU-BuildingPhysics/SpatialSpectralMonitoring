
# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# HDR Viewer: A tool for visualizing and analyzing High Dynamic Range (HDR) images.
# Provides features such as exposure adjustment, gamma correction, luminance analysis, and false color visualization.
#
# ==============================================================================

import numpy as np
import cv2
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button, RadioButtons
from matplotlib.backend_bases import MouseButton
from matplotlib.colors import LinearSegmentedColormap, LogNorm
import os
import json
import tarfile
import tempfile
import atexit
import shutil
from pathlib import Path

class HDRViewer:
    """
    A class for viewing and analyzing HDR images with various visualization tools.
    """

    SAVE_DPI = 300
    HISTOGRAM_LOCKED_Y_MIN = 0
    HISTOGRAM_LOCKED_Y_MAX = 35000
    HISTOGRAM_LOCKED_X_MIN = 0
    HISTOGRAM_LOCKED_X_MAX = 1e6
    HISTOGRAM_LOCKED_Y_AUTO = True
    HISTOGRAM_LOCKED_X_AUTO = True

    def __init__(self):
        """
        Initialize the HDRViewer with default settings and prepare the figure.
        """
        self.hdr_images = []
        self.hdr_names = []
        self.hdr_metadata = []
        self.current_image_idx = 0
        self.exposure = 0.0 
        self.gamma = 2.2
        self.colormap = 'viridis'
        self.show_false_color = True
        self.channel_mode = 'Luminance' 
        self.colorbar = None
        self.cbar_ax = None 
        self.manual_vmin = None  
        self.manual_vmax = None  
        self.luminance_scale_factor = 1.0  
        self.luminance_stats = None  
        self.illuminance_lux = None  
        self.roi_params = None  
        self.click_markers = []  
        self.magnifier_ax = None  
        self.magnifier_active = False  
        self.hover_x = None  
        self.hover_y = None
        self.luminance_cache = None  
        self.luminance_cache_idx = -1  
        self.saturation_mask = None  
        self.saturation_count = 0  
        self.saturation_percentage = 0.0  
        self.saturation_roi_overlap = False  
        self.show_saturation = False  
        self.current_hdr_path = None
        self.use_log_scale = True
        self.log_vmin = None
        self.log_vmax = None
        self.ldr_cache = None
        self.ldr_cache_key = None
        self.white_threshold = 0.85
        self.dominant_color_r_threshold = 0.3
        self.dominant_color_g_threshold = 0.3
        self.dominant_color_b_threshold = 0.3
        self.hdr_stats_cache = None
        self.hdr_stats_cache_idx = -1
        self._hover_timer = None
        self._hover_interval = 0.05
        self.histogram_y_locked = self.HISTOGRAM_LOCKED_Y_AUTO
        self.histogram_x_locked = self.HISTOGRAM_LOCKED_X_AUTO
        self.histogram_hover_text = None
        self.histogram_bins = None  # Store bin edges for hover lookup
        self.histogram_counts = None  # Store bar heights for hover lookup
        self.histogram_highlighted_bar = None  # Store highlighted bar patch

        self.sensor_filter = None  # None = show all sensors

        self._temp_dirs = []
        atexit.register(self._cleanup_temp_dirs)

        self.create_channel_colormaps()

        self.setup_figure()

    def create_channel_colormaps(self):
        """
        Create custom colormaps for R, G, B channels (black → colour → white gradient).
        """
        self.cmap_red = LinearSegmentedColormap.from_list('red_channel', [(0, 'black'), (0.5, 'red'), (1, 'white')])
        self.cmap_green = LinearSegmentedColormap.from_list('green_channel', [(0, 'black'), (0.5, 'green'), (1, 'white')])
        self.cmap_blue = LinearSegmentedColormap.from_list('blue_channel', [(0, 'black'), (0.5, 'blue'), (1, 'white')])

    @staticmethod
    def _fmt_lum(value):
        """Format a luminance value with precision scaled to its magnitude."""
        abs_val = abs(value)
        if abs_val >= 100:
            return f'{value:.0f}'
        elif abs_val >= 10:
            return f'{value:.1f}'
        elif abs_val >= 1:
            return f'{value:.1f}'
        elif abs_val >= 0.1:
            return f'{value:.2f}'
        elif abs_val >= 0.01:
            return f'{value:.2f}'
        else:
            return f'{value:.2e}'

    def setup_figure(self):
        """
        Initialize the matplotlib figure and widgets.
        """
        self.fig = plt.figure(figsize=(16, 10))
        self.fig.subplots_adjust(top=0.87)  # Reserve top strip for sensor filter buttons

        self.ax_image = plt.subplot2grid((3, 3), (0, 0), colspan=2, rowspan=2)
        self.ax_image.set_title('HDR Image Viewer')

        img_pos = self.ax_image.get_position()
        cbar_width = 0.015
        cbar_padding = -0.015  
        self.cbar_ax = self.fig.add_axes([img_pos.x1 + cbar_padding, img_pos.y0, cbar_width, img_pos.height])
        self.cbar_ax.set_visible(False)

        self.ax_hist = plt.subplot2grid((3, 3), (2, 0), colspan=2)
        self.ax_hist.set_title('Histogram (log scale)')
        self.ax_hist.set_xlabel('Pixel Value')
        self.ax_hist.set_ylabel('Count')

        self.ax_info = plt.subplot2grid((3, 3), (0, 2), rowspan=3)
        self.ax_info.axis('off')
        self.info_text = self.ax_info.text(0.05, 0.95, '', transform=self.ax_info.transAxes,
                                           verticalalignment='top', fontfamily='monospace',
                                           fontsize=9)

        ax_exposure = plt.axes([0.15, 0.02, 0.3, 0.02])
        self.slider_exposure = Slider(ax_exposure, 'Exposure', -20.0, 20.0, 
                                      valinit=self.exposure, valstep=0.1)
        self.slider_exposure.on_changed(self.update_exposure)

        ax_gamma = plt.axes([0.15, 0.045, 0.3, 0.02])
        self.slider_gamma = Slider(ax_gamma, 'Gamma', 0.5, 3.0, 
                                   valinit=self.gamma, valstep=0.1)
        self.slider_gamma.on_changed(self.update_gamma)

        ax_lum_scale = plt.axes([0.15, 0.07, 0.3, 0.02])
        self.slider_lum_scale = Slider(ax_lum_scale, 'Lum Scale', 0.05, 1.0, 
                                       valinit=self.luminance_scale_factor, valstep=0.05)
        self.slider_lum_scale.on_changed(self.update_luminance_scale)

        ax_white_threshold = plt.axes([0.15, 0.155, 0.3, 0.02])
        self.slider_white_threshold = Slider(ax_white_threshold, 'White Thr', 0.5, 1.0, 
                                             valinit=self.white_threshold, valstep=0.05)
        self.slider_white_threshold.on_changed(self.update_white_threshold)
        self.slider_white_threshold.ax.set_visible(False)

        ax_r_threshold = plt.axes([0.15, 0.185, 0.3, 0.02])
        self.slider_r_threshold = Slider(ax_r_threshold, 'Red Thr', 0.0, 1.0, 
                                         valinit=self.dominant_color_r_threshold, valstep=0.05)
        self.slider_r_threshold.on_changed(self.update_r_threshold)
        self.slider_r_threshold.ax.set_visible(False)
        
        self._r_threshold_text = ax_r_threshold.text(0.98, 0.5, '', transform=ax_r_threshold.transAxes,
                                                      fontsize=9, ha='right', va='center',
                                                      bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))
        self._r_threshold_text.set_visible(False)

        ax_g_threshold = plt.axes([0.15, 0.215, 0.3, 0.02])
        self.slider_g_threshold = Slider(ax_g_threshold, 'Green Thr', 0.0, 1.0, 
                                         valinit=self.dominant_color_g_threshold, valstep=0.05)
        self.slider_g_threshold.on_changed(self.update_g_threshold)
        self.slider_g_threshold.ax.set_visible(False)
        
        self._g_threshold_text = ax_g_threshold.text(0.98, 0.5, '', transform=ax_g_threshold.transAxes,
                                                      fontsize=9, ha='right', va='center',
                                                      bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))
        self._g_threshold_text.set_visible(False)

        ax_b_threshold = plt.axes([0.15, 0.245, 0.3, 0.02])
        self.slider_b_threshold = Slider(ax_b_threshold, 'Blue Thr', 0.0, 1.0, 
                                         valinit=self.dominant_color_b_threshold, valstep=0.05)
        self.slider_b_threshold.on_changed(self.update_b_threshold)
        self.slider_b_threshold.ax.set_visible(False)
        
        self._b_threshold_text = ax_b_threshold.text(0.98, 0.5, '', transform=ax_b_threshold.transAxes,
                                                      fontsize=9, ha='right', va='center',
                                                      bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))
        self._b_threshold_text.set_visible(False)

        ax_load = plt.axes([0.5, 0.02, 0.08, 0.04])
        self.btn_load = Button(ax_load, 'Load HDR')
        self.btn_load.on_clicked(self.load_hdr_dialog)

        ax_prev = plt.axes([0.6, 0.02, 0.05, 0.04])
        self.btn_prev = Button(ax_prev, 'Prev')
        self.btn_prev.on_clicked(self.previous_image)

        ax_next = plt.axes([0.66, 0.02, 0.05, 0.04])
        self.btn_next = Button(ax_next, 'Next')
        self.btn_next.on_clicked(self.next_image)

        ax_false_color = plt.axes([0.73, 0.02, 0.1, 0.04])
        self.btn_false_color = Button(ax_false_color, 'False Color')
        self.btn_false_color.on_clicked(self.toggle_false_color)

        ax_saturation = plt.axes([0.73, 0.07, 0.1, 0.04])
        self.btn_saturation = Button(ax_saturation, 'Show Saturation')
        self.btn_saturation.on_clicked(self.toggle_saturation)

        ax_log_scale = plt.axes([0.73, 0.12, 0.1, 0.04])
        self.btn_log_scale = Button(ax_log_scale, 'Log Scale: OFF')
        self.btn_log_scale.on_clicked(self.toggle_log_scale)

        ax_channels = plt.axes([0.85, 0.02, 0.1, 0.18])
        self.radio_channels = RadioButtons(ax_channels, ('RGB', 'R', 'G', 'B', 'Gray', 'Luminance', 'Dominant Color'))
        self.radio_channels.on_clicked(self.change_channel)

        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('button_press_event', self.on_histogram_click)

        self.fig.canvas.mpl_connect('motion_notify_event', self.on_hover)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_histogram_hover)

        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)

        self.magnifier_ax = self.fig.add_axes([0.45, 0.6, 0.15, 0.15])
        self.magnifier_ax.set_visible(False)
        self.magnifier_ax.set_title('Magnifier', fontsize=8)

        plt.rcParams['keymap.back'] = []
        plt.rcParams['keymap.forward'] = []

        ax_reset_limits = plt.axes([0.85, 0.22, 0.1, 0.04])
        self.btn_reset_limits = Button(ax_reset_limits, 'Reset Limits')
        self.btn_reset_limits.on_clicked(self.reset_manual_limits)

        ax_clear_clicks = plt.axes([0.85, 0.27, 0.1, 0.04])
        self.btn_clear_clicks = Button(ax_clear_clicks, 'Clear Clicks')
        self.btn_clear_clicks.on_clicked(self.clear_clicks)

        ax_save = plt.axes([0.85, 0.32, 0.1, 0.04])
        self.btn_save = Button(ax_save, 'Save PNG')
        self.btn_save.on_clicked(self.save_figure)

        ax_save_img = plt.axes([0.85, 0.37, 0.1, 0.04])
        self.btn_save_img = Button(ax_save_img, 'Save Image Only')
        self.btn_save_img.on_clicked(self.save_image_only)

        ax_clear_images = plt.axes([0.85, 0.42, 0.1, 0.04])
        self.btn_clear_images = Button(ax_clear_images, 'Clear Images')
        self.btn_clear_images.on_clicked(self.clear_images)

        # Sensor filter strip (pre-allocated, hidden until multiple sensors are loaded)
        MAX_SENSOR_BTNS = 8
        self._filter_label_text = self.fig.text(0.04, 0.932, 'Sensor:', fontsize=9,
                                                va='center', fontweight='bold')
        self._filter_label_text.set_visible(False)

        ax_filter_all = plt.axes([0.09, 0.912, 0.045, 0.04])
        self._filter_btn_all = Button(ax_filter_all, 'All')
        self._filter_btn_all.on_clicked(self._on_filter_all)
        ax_filter_all.set_visible(False)
        self._filter_btn_all_ax = ax_filter_all

        self._filter_btn_axes = []
        self._filter_btns = []
        for i in range(MAX_SENSOR_BTNS):
            ax = plt.axes([0.14 + i * 0.065, 0.912, 0.06, 0.04])
            btn = Button(ax, '')
            btn.on_clicked(self._make_sensor_handler(i))
            ax.set_visible(False)
            self._filter_btn_axes.append(ax)
            self._filter_btns.append(btn)

        self.update_display()

    def load_hdr(self, filepath):
        """
        Load an HDR file from the specified filepath.
        """
        try:
            hdr = cv2.imread(filepath, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
            if hdr is None:
                print(f"Error: Could not load {filepath}")
                return False

            hdr = cv2.cvtColor(hdr, cv2.COLOR_BGR2RGB)

            self.hdr_images.append(hdr)
            self.hdr_names.append(os.path.basename(filepath))
            self.hdr_metadata.append(self.parse_hdr_header(filepath))
            self.current_image_idx = len(self.hdr_images) - 1
            self.current_hdr_path = filepath
            self.ldr_cache = None
            self.ldr_cache_key = None

            print(f"Loaded: {filepath}")
            print(f"Shape: {hdr.shape}, Range: [{hdr.min():.6f}, {hdr.max():.6f}]")

            self.try_load_roi_params(filepath)

            self.load_saturation_data(filepath)

            self.update_sensor_buttons()
            self.update_display()
            return True
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return False

    def parse_hdr_header(self, filepath):
        """Parse key-value metadata fields from a Radiance .hdr file header."""
        metadata = {}
        try:
            with open(filepath, 'rb') as f:
                for raw_line in f:
                    line = raw_line.decode('latin-1').rstrip('\n\r')
                    if line == '' or line.startswith('-Y') or line.startswith('+Y'):
                        break
                    if '=' in line and not line.startswith('#'):
                        key, _, value = line.partition('=')
                        metadata[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: could not parse HDR header for {filepath}: {e}")
        return metadata

    def _cleanup_temp_dirs(self):
        """Remove all temporary directories created for TAR extraction."""
        for d in self._temp_dirs:
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass
        self._temp_dirs.clear()

    def load_tar(self, tar_filepath):
        """
        Extract all HDR/EXR files from a TAR archive to a temporary directory
        and load each one into the viewer.
        """
        HDR_EXTENSIONS = {'.hdr', '.exr'}
        try:
            tmp_dir = tempfile.mkdtemp(prefix='hdr_viewer_tar_')
            self._temp_dirs.append(tmp_dir)
            print(f"Extracting TAR archive: {tar_filepath}")
            with tarfile.open(tar_filepath, 'r:*') as tf:
                members = [
                    m for m in tf.getmembers()
                    if m.isfile() and Path(m.name).suffix.lower() in HDR_EXTENSIONS
                ]
                if not members:
                    print("No HDR or EXR files found in TAR archive.")
                    return False
                print(f"Found {len(members)} HDR/EXR file(s) in archive.")
                tf.extractall(path=tmp_dir, members=members)

            loaded = 0
            for m in members:
                extracted_path = os.path.join(tmp_dir, m.name)
                if os.path.exists(extracted_path):
                    if self.load_hdr(extracted_path):
                        loaded += 1
                else:
                    # extractall may flatten directory structure on some platforms
                    flat_path = os.path.join(tmp_dir, os.path.basename(m.name))
                    if os.path.exists(flat_path) and self.load_hdr(flat_path):
                        loaded += 1
            print(f"Loaded {loaded}/{len(members)} HDR file(s) from TAR archive.")
            return loaded > 0
        except Exception as e:
            print(f"Error loading TAR file {tar_filepath}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_hdr_dialog(self, event):
        """
        Open file dialog to load HDR/EXR files or TAR archives.
        """
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        filepaths = filedialog.askopenfilenames(
            title='Select HDR files or TAR archives',
            filetypes=[
                ('HDR/TAR files', '*.hdr *.exr *.tar *.tar.gz *.tgz'),
                ('HDR files', '*.hdr'),
                ('EXR files', '*.exr'),
                ('TAR archives', '*.tar *.tar.gz *.tgz'),
                ('All files', '*.*'),
            ]
        )

        for filepath in filepaths:
            if tarfile.is_tarfile(filepath):
                self.load_tar(filepath)
            else:
                self.load_hdr(filepath)

        root.destroy()

    def tone_map(self, hdr_image):
        """
        Apply tone mapping to an HDR image for display.
        """
        if hdr_image is None:
            return None

        exposed = hdr_image * (2.0 ** self.exposure)
        ldr = np.clip(exposed, 0, None)
        ldr = np.power(ldr, 1.0 / self.gamma)
        ldr = np.clip(ldr, 0, 1)

        return ldr

    def get_ldr(self, hdr):
        """Return tone-mapped LDR image, reusing cache when exposure/gamma/image are unchanged."""
        cache_key = (self.current_image_idx, self.exposure, self.gamma)
        if self.ldr_cache is not None and self.ldr_cache_key == cache_key:
            return self.ldr_cache
        ldr = self.tone_map(hdr)
        self.ldr_cache = ldr
        self.ldr_cache_key = cache_key
        return ldr

    def get_dominant_color_image(self, hdr):
        """
        Generate a dominant color visualization where Red, Green, or Blue is shown
        based on which channel has the highest value at each pixel.
        Reacts to exposure and gamma settings via tone mapping.
        White is shown when all channels are above the white threshold.
        Uses individual thresholds for each R, G, B channel.
        """
        # Use tone-mapped LDR image so it responds to exposure and gamma
        ldr = self.get_ldr(hdr)
        
        height, width = ldr.shape[:2]
        dominant_color = np.zeros((height, width, 3), dtype=np.float32)
        
        r_channel = ldr[:, :, 0]
        g_channel = ldr[:, :, 1]
        b_channel = ldr[:, :, 2]
        
        # Detect white: all channels above white threshold
        white_mask = (r_channel >= self.white_threshold) & \
                     (g_channel >= self.white_threshold) & \
                     (b_channel >= self.white_threshold)
        
        # Find dominant channel for each pixel (only where not white)
        max_channel = np.maximum(np.maximum(r_channel, g_channel), b_channel)
        
        # Create masks for each dominant color (excluding white)
        # Use individual thresholds for each channel
        r_dominant = (r_channel == max_channel) & ~white_mask & (r_channel >= self.dominant_color_r_threshold)
        g_dominant = (g_channel == max_channel) & ~white_mask & (g_channel >= self.dominant_color_g_threshold)
        b_dominant = (b_channel == max_channel) & ~white_mask & (b_channel >= self.dominant_color_b_threshold)
        
        # Assign colors: Red=1,0,0; Green=0,1,0; Blue=0,0,1, weighted by intensity
        dominant_color[:, :, 0] = np.where(r_dominant, r_channel, 0)  # Red channel
        dominant_color[:, :, 1] = np.where(g_dominant, g_channel, 0)  # Green channel
        dominant_color[:, :, 2] = np.where(b_dominant, b_channel, 0)  # Blue channel
        
        # Assign white color where all channels are high
        dominant_color[:, :, 0] = np.where(white_mask, 1.0, dominant_color[:, :, 0])
        dominant_color[:, :, 1] = np.where(white_mask, 1.0, dominant_color[:, :, 1])
        dominant_color[:, :, 2] = np.where(white_mask, 1.0, dominant_color[:, :, 2])
        
        # Clip to valid range
        dominant_color = np.clip(dominant_color, 0, 1)
        
        return dominant_color

    def get_display_image(self):
        """
        Get the current image for display based on the selected channel mode.
        """
        if not self.hdr_images:
            return None

        hdr = self.hdr_images[self.current_image_idx]

        if self.channel_mode == 'Luminance':

            if self.luminance_cache is None or self.luminance_cache_idx != self.current_image_idx:

                luminance = 0.2126 * hdr[:, :, 0] + 0.7152 * hdr[:, :, 1] + 0.0722 * hdr[:, :, 2]

                self.luminance_cache = luminance
                self.luminance_cache_idx = self.current_image_idx

                self.calculate_luminance_stats(luminance)
            return self.luminance_cache

        if self.channel_mode == 'Dominant Color':
            return self.get_dominant_color_image(hdr)

        ldr = self.get_ldr(hdr)

        if ldr is None:
            return None

        if self.channel_mode == 'RGB':
            display = ldr
        elif self.channel_mode == 'R':
            display = ldr[:, :, 0]
        elif self.channel_mode == 'G':
            display = ldr[:, :, 1]
        elif self.channel_mode == 'B':
            display = ldr[:, :, 2]
        elif self.channel_mode == 'Gray':
            display = 0.299 * ldr[:, :, 0] + 0.587 * ldr[:, :, 1] + 0.114 * ldr[:, :, 2]

        return display

    def update_display(self):
        """
        Update the image display with the current settings.
        """
        self.ax_image.clear()

        self.cbar_ax.set_axes_locator(None)
        self.cbar_ax.clear()
        self.cbar_ax.set_visible(False)
        self.colorbar = None

        if not self.hdr_images:
            self.ax_image.text(0.5, 0.5, 'No HDR image loaded\nClick "Load HDR" to start',
                              ha='center', va='center', transform=self.ax_image.transAxes,
                              fontsize=14)
            self.ax_image.set_title('HDR Image Viewer')
        else:
            display = self.get_display_image()

            if display is not None:
                if self.channel_mode == 'Luminance':
                    if self.use_log_scale:
                        pos_vals = display[display > 0]
                        if self.manual_vmin is not None and self.manual_vmax is not None:
                            log_vmin = max(self.manual_vmin, 1e-6)
                            log_vmax = self.manual_vmax
                        else:
                            log_vmin = float(np.nanpercentile(pos_vals, 1)) if len(pos_vals) > 0 else 1e-6
                            log_vmax = float(np.nanmax(display)) * self.luminance_scale_factor
                        norm = LogNorm(vmin=log_vmin, vmax=max(log_vmax, log_vmin * 10))
                        self.log_vmin, self.log_vmax = log_vmin, max(log_vmax, log_vmin * 10)
                        display_log = np.where(display < log_vmin, log_vmin, display)
                        im = self.ax_image.imshow(display_log, cmap=self.colormap, norm=norm)
                    else:
                        self.log_vmin, self.log_vmax = None, None
                        if self.manual_vmin is not None and self.manual_vmax is not None:
                            vmin = self.manual_vmin
                            vmax = self.manual_vmax
                        else:
                            vmin = 0
                            vmax = np.nanmax(display) * self.luminance_scale_factor
                        im = self.ax_image.imshow(display, cmap=self.colormap, vmin=vmin, vmax=vmax)
                    self.cbar_ax.set_visible(True)
                    self.colorbar = self.fig.colorbar(im, cax=self.cbar_ax)
                    lum_label = 'Luminance (cd/m²) [log]' if self.use_log_scale else 'Luminance (cd/m²)'
                    self.colorbar.set_label(lum_label, rotation=270, labelpad=20)

                    for x, y, lum_val in self.click_markers:
                        self.ax_image.plot(x, y, 'r+', markersize=15, markeredgewidth=2)
                        self.ax_image.text(x + 10, y - 10, self._fmt_lum(lum_val), 
                                          color='red', fontsize=10, fontweight='bold',
                                          bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

                    if self.show_saturation and self.saturation_mask is not None:
                        self.ax_image.contour(self.saturation_mask.astype(float), 
                                            levels=[0.5], 
                                            colors=['#FF00FF'], 
                                            linewidths=2.0,
                                            linestyles='solid')
                elif self.show_false_color and len(display.shape) == 2:
                    if self.use_log_scale:
                        pos_vals = display[display > 0]
                        if self.manual_vmin is not None and self.manual_vmax is not None:
                            log_vmin = max(self.manual_vmin, 1e-6)
                            log_vmax = self.manual_vmax
                        else:
                            log_vmin = float(np.nanpercentile(pos_vals, 1)) if len(pos_vals) > 0 else 1e-6
                            log_vmax = float(np.nanmax(display))
                        norm = LogNorm(vmin=log_vmin, vmax=max(log_vmax, log_vmin * 10))
                        display_log = np.where(display <= 0, log_vmin, display)
                        im = self.ax_image.imshow(display_log, cmap=self.colormap, norm=norm)
                    elif self.manual_vmin is not None and self.manual_vmax is not None:
                        im = self.ax_image.imshow(display, cmap=self.colormap, vmin=self.manual_vmin, vmax=self.manual_vmax)
                    else:
                        im = self.ax_image.imshow(display, cmap=self.colormap)
                    self.cbar_ax.set_visible(True)
                    self.colorbar = self.fig.colorbar(im, cax=self.cbar_ax)
                    fc_label = 'Intensity [log]' if self.use_log_scale else 'Intensity'
                    self.colorbar.set_label(fc_label, rotation=270, labelpad=20)
                elif len(display.shape) == 2:

                    cmap_to_use = 'gray'
                    colorbar_label = 'Intensity'

                    if self.channel_mode == 'R':
                        cmap_to_use = self.cmap_red
                        colorbar_label = 'Red Channel'
                    elif self.channel_mode == 'G':
                        cmap_to_use = self.cmap_green
                        colorbar_label = 'Green Channel'
                    elif self.channel_mode == 'B':
                        cmap_to_use = self.cmap_blue
                        colorbar_label = 'Blue Channel'

                    im = self.ax_image.imshow(display, cmap=cmap_to_use, interpolation='nearest', vmin=0, vmax=1)

                    if self.channel_mode in ['R', 'G', 'B']:
                        self.cbar_ax.set_visible(True)
                        self.colorbar = self.fig.colorbar(im, cax=self.cbar_ax)
                        self.colorbar.set_label(colorbar_label, rotation=270, labelpad=20)
                elif self.channel_mode == 'Dominant Color':
                    # Display dominant color as RGB image without colorbar
                    self.ax_image.imshow(display, interpolation='nearest')
                else:

                    self.ax_image.imshow(display, interpolation='nearest')

                filtered = self._get_filtered_indices()
                if self.sensor_filter is not None and self.current_image_idx in filtered:
                    fpos = filtered.index(self.current_image_idx) + 1
                    title = (f'{self.hdr_names[self.current_image_idx]}'
                             f' ({fpos}/{len(filtered)} [{self.sensor_filter}]'
                             f' | {self.current_image_idx + 1}/{len(self.hdr_images)} total)')
                else:
                    title = f'{self.hdr_names[self.current_image_idx]} ({self.current_image_idx + 1}/{len(self.hdr_images)})'
                if self.channel_mode == 'Luminance':
                    suffix = ' [log]' if self.use_log_scale else ''
                    title += f' - Luminance (cd/m²){suffix}'
                elif self.channel_mode == 'Dominant Color':
                    title += ' - Dominant Color (R/G/B)'
                self.ax_image.set_title(title)

        self.update_histogram()
        self.update_info()
        self.fig.canvas.draw_idle()

    def update_histogram(self):
        """
        Update the histogram display based on the current image.
        """
        self.ax_hist.clear()

        if not self.hdr_images:
            return

        hdr = self.hdr_images[self.current_image_idx]

        if self.channel_mode == 'Luminance':
            if self.luminance_cache is not None and self.luminance_cache_idx == self.current_image_idx:
                luminance = self.luminance_cache
            else:
                luminance = 0.2126 * hdr[:, :, 0] + 0.7152 * hdr[:, :, 1] + 0.0722 * hdr[:, :, 2]
            data = luminance.flatten()
            data = data[data > 0]
            if len(data) > 0:
                if self.use_log_scale:
                    if self.histogram_x_locked:
                        # Use fixed bins so log tick positions stay constant across images
                        x_log_min = max(self.HISTOGRAM_LOCKED_X_MIN, 1)  # log can't start at 0
                        bins = np.logspace(np.log10(x_log_min), np.log10(self.HISTOGRAM_LOCKED_X_MAX), 100)
                    else:
                        bins = np.logspace(np.log10(data.min()), np.log10(data.max()), 100)
                    counts, bins_out, patches = self.ax_hist.hist(data, bins=bins, alpha=0.7, color='orange')
                    self.histogram_counts = counts
                    self.histogram_bins = bins_out
                    self.ax_hist.set_xscale('log')
                else:
                    counts, bins_out, patches = self.ax_hist.hist(data, bins=100, alpha=0.7, color='orange')
                    self.histogram_counts = counts
                    self.histogram_bins = bins_out
            self.ax_hist.set_xlabel('Luminance (cd/m²)')
            self.ax_hist.set_ylabel('Count')
            hist_title = 'Luminance Histogram (log scale)' if self.use_log_scale else 'Luminance Histogram'
            self.ax_hist.set_title(hist_title)
        else:
            self.histogram_bins = None
            self.histogram_counts = None
            ldr = self.get_ldr(hdr)

            if ldr is not None:
                if self.channel_mode == 'RGB':
                    colors = ['red', 'green', 'blue']
                    for i, color in enumerate(colors):
                        data = ldr[:, :, i].flatten()
                        data = data[data > 0] 
                        if len(data) > 0:
                            self.ax_hist.hist(data, bins=100, alpha=0.5, color=color, 
                                             label=color.capitalize())
                    self.ax_hist.legend()
                else:
                    if len(ldr.shape) == 3:
                        data = ldr.flatten()
                    else:
                        data = ldr.flatten()
                    data = data[data > 0]
                    if len(data) > 0:
                        self.ax_hist.hist(data, bins=100, alpha=0.7, color='gray')

            self.ax_hist.set_xlabel('Pixel Value')
            self.ax_hist.set_ylabel('Count')
            self.ax_hist.set_title(f'Histogram - {self.channel_mode} Channel(s)')

        # Apply locked axis limits if enabled
        if self.histogram_y_locked:
            self.ax_hist.set_ylim(self.HISTOGRAM_LOCKED_Y_MIN, self.HISTOGRAM_LOCKED_Y_MAX)
        if self.histogram_x_locked:
            self.ax_hist.set_xlim(self.HISTOGRAM_LOCKED_X_MIN, self.HISTOGRAM_LOCKED_X_MAX)
        
        self.ax_hist.grid(True, alpha=0.3)

    def _get_hdr_stats(self, hdr):
        """Return cached per-image HDR statistics dict."""
        if self.hdr_stats_cache is not None and self.hdr_stats_cache_idx == self.current_image_idx:
            return self.hdr_stats_cache
        stats = {
            'min': float(hdr.min()),
            'max': float(hdr.max()),
            'mean': float(hdr.mean()),
            'median': float(np.median(hdr)),
            'std': float(hdr.std()),
        }
        if len(hdr.shape) == 3:
            channels = {}
            for i, color in enumerate(['R', 'G', 'B']):
                ch = hdr[:, :, i]
                channels[color] = {
                    'min': float(ch.min()),
                    'max': float(ch.max()),
                    'mean': float(ch.mean()),
                }
            stats['channels'] = channels
        self.hdr_stats_cache = stats
        self.hdr_stats_cache_idx = self.current_image_idx
        return stats

    def update_info(self):
        """
        Update the information panel with image statistics and settings.
        """
        if not self.hdr_images:
            info = 'No image loaded'
        else:
            hdr = self.hdr_images[self.current_image_idx]
            s = self._get_hdr_stats(hdr)

            info = f"File: {self.hdr_names[self.current_image_idx]}\n"
            info += f"Image: {self.current_image_idx + 1} / {len(self.hdr_images)}\n"
            info += f"Size: {hdr.shape[1]} x {hdr.shape[0]}\n"
            info += f"Channels: {hdr.shape[2] if len(hdr.shape) > 2 else 1}\n"

            meta = self.hdr_metadata[self.current_image_idx] if self.current_image_idx < len(self.hdr_metadata) else {}

            capture_fields = []
            if meta.get('DEVICE'):
                capture_fields.append(('Device', meta['DEVICE']))
            if meta.get('CAPDATE'):
                capture_fields.append(('Date (local)', meta['CAPDATE'].strip()))
            if meta.get('GMT'):
                capture_fields.append(('Date (UTC)', meta['GMT'].strip()))
            if meta.get('HDR_BRACKETS'):
                capture_fields.append(('Brackets', meta['HDR_BRACKETS']))
            if meta.get('SOFTWARE'):
                capture_fields.append(('Firmware', meta['SOFTWARE']))
            if capture_fields:
                info += "=== Capture Info ===\n"
                for label, value in capture_fields:
                    info += f"{label}: {value}\n"
                info += "\n"

            cal_fields = []
            if meta.get('CAL_FLAGS'):
                cal_fields.append(('Flags', meta['CAL_FLAGS']))
            if meta.get('CAL_SCALE'):
                cal_fields.append(('Scale', meta['CAL_SCALE']))
            if meta.get('CAL_VIGN_CENTER'):
                cal_fields.append(('Vign center', meta['CAL_VIGN_CENTER']))
            if meta.get('CAL_VIGN_MAXDIST'):
                cal_fields.append(('Vign maxdist', meta['CAL_VIGN_MAXDIST']))
            if cal_fields:
                info += "=== Calibration ===\n"
                for label, value in cal_fields:
                    info += f"{label}: {value}\n"
                if self.roi_params is not None:
                    roi_src = self.roi_params.get('_source', 'unknown')
                    info += f"ROI source: {roi_src}\n"
                else:
                    info += "ROI: not loaded\n"
                info += "\n"
            elif not capture_fields:
                info += "\n"

            info += "=== HDR Statistics ===\n"
            info += f"Min: {s['min']:.6f}\n"
            info += f"Max: {s['max']:.6f}\n"
            info += f"Mean: {s['mean']:.6f}\n"
            info += f"Median: {s['median']:.6f}\n"
            info += f"Std: {s['std']:.6f}\n\n"

            if 'channels' in s:
                info += "=== Per Channel (HDR) ===\n"
                for color in ['R', 'G', 'B']:
                    ch = s['channels'][color]
                    info += f"{color}: [{ch['min']:.4f}, {ch['max']:.4f}]\n"
                    info += f"   mean: {ch['mean']:.4f}\n"

            if self.luminance_stats is not None:
                info += "\n=== Luminance (cd/m²) ===\n"
                info += f"Mean: {self.luminance_stats['mean']:.2f}\n"
                info += f"Median: {self.luminance_stats['median']:.2f}\n"
                info += f"Min: {self.luminance_stats['min']:.2f}\n"
                info += f"Max: {self.luminance_stats['max']:.2f}\n"
                info += f"Std: {self.luminance_stats['std']:.2f}\n"

            if self.illuminance_lux is not None:
                info += "\n=== Illuminance ===\n"
                info += f"Horizontal: {self.illuminance_lux:.2f} lux\n"

            if self.saturation_mask is not None:
                info += "\n=== Saturation Analysis ===\n"
                info += f"Saturated pixels: {self.saturation_count:,}\n"
                info += f"Percentage: {self.saturation_percentage:.2f}%\n"
                if self.saturation_count > 0:
                    info += "⚠️ Saturated pixels detected\n"
                    if self.saturation_roi_overlap:
                        info += "⚠️ ROI contains saturated pixels\n"
                        info += "   Illuminance may be underestimated\n"
                else:
                    info += "✓ No saturation detected\n"
            elif self.saturation_mask is False:
                info += "\n=== Saturation Analysis ===\n"
                info += "Data not available\n"

            info += f"\n=== Display Settings ===\n"
            info += f"Exposure: {self.exposure:.1f} EV\n"
            info += f"Gamma: {self.gamma:.1f}\n"
            info += f"Channel: {self.channel_mode}\n"
            info += f"False Color: {self.show_false_color}\n"
            info += f"Log Scale: {'ON' if self.use_log_scale else 'OFF'}\n"
            if self.channel_mode == 'Luminance':
                info += f"Lum Scale: {self.luminance_scale_factor:.2f}\n"
            if self.channel_mode == 'Dominant Color':
                info += f"White Thr: {self.white_threshold:.2f}\n"
            if self.manual_vmin is not None and self.manual_vmax is not None:
                info += f"Colorbar: [{self.manual_vmin:.4f}, {self.manual_vmax:.4f}]\n"
            elif self.channel_mode == 'Luminance' and self.luminance_stats is not None:
                vmax = self.luminance_stats['max'] * self.luminance_scale_factor
                info += f"Colorbar: [0.00, {vmax:.2f}] (auto)\n"
            else:
                info += f"Colorbar: Auto\n"
            info += "\n"

            info += "=== Controls ===\n"
            info += "• Hover: magnifying glass\n"
            info += "• Click pixel for values\n"
            info += "• Click in Luminance mode: mark\n"
            info += "• Double-click colorbar for limits\n"
            info += "• Clear Clicks to remove markers\n"
            info += "• Save PNG for export\n"
            info += "• Adjust sliders for exposure\n"
            info += "• Prev/Next for multi-image\n"
            info += "• False Color for heatmap\n"
            info += "• Radio buttons for channels\n"

        self.info_text.set_text(info)

    def on_key_press(self, event):
        """Handle keyboard events for image navigation."""
        if event.key == 'right':
            self.next_image(None)
        elif event.key == 'left':
            self.previous_image(None)

    def on_click(self, event):
        """
        Handle mouse click events for pixel value display or colorbar adjustments.
        """

        if event.dblclick and event.inaxes == self.cbar_ax and self.colorbar is not None:
            self.set_manual_limits()
            return

        if event.inaxes != self.ax_image or not self.hdr_images:
            return

        if event.button == MouseButton.LEFT:
            x, y = int(event.xdata), int(event.ydata)
            hdr = self.hdr_images[self.current_image_idx]

            if 0 <= y < hdr.shape[0] and 0 <= x < hdr.shape[1]:
                if len(hdr.shape) == 3:
                    r, g, b = hdr[y, x]
                    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b

                    print(f"\nPixel [{x}, {y}]:")
                    print(f"  HDR RGB: ({r:.6f}, {g:.6f}, {b:.6f})")
                    print(f"  Luminance: {luminance:.6f} cd/m²")
                    print(f"  HDR Gray: {0.299*r + 0.587*g + 0.114*b:.6f}")

                    if self.channel_mode == 'Luminance':

                        click_tolerance = 10
                        marker_to_remove = None
                        for i, (mx, my, _) in enumerate(self.click_markers):
                            distance = np.sqrt((x - mx)**2 + (y - my)**2)
                            if distance <= click_tolerance:
                                marker_to_remove = i
                                break

                        if marker_to_remove is not None:

                            removed = self.click_markers.pop(marker_to_remove)
                            print(f"  >>> Marker removed at [{removed[0]}, {removed[1]}] (total: {len(self.click_markers)})")
                        else:

                            self.click_markers.append((x, y, luminance))
                            print(f"  >>> Marker added (total: {len(self.click_markers)})")

                        self.update_display()

                    if self.channel_mode != 'Luminance':
                        ldr = self.tone_map(hdr)
                        r_ldr, g_ldr, b_ldr = ldr[y, x]
                        print(f"  LDR RGB: ({r_ldr:.4f}, {g_ldr:.4f}, {b_ldr:.4f})")
                else:
                    val = hdr[y, x]
                    print(f"\nPixel [{x}, {y}]: {val:.6f}")

    def on_hover(self, event):
        """
        Handle mouse hover events to show a magnifying glass.
        """

        if event.inaxes != self.ax_image or not self.hdr_images or self.channel_mode != 'Luminance':
            if self.magnifier_active:
                self.magnifier_ax.set_visible(False)
                self.magnifier_active = False
                self.fig.canvas.draw_idle()
            return

        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return

        x_int, y_int = int(x), int(y)

        # Throttle: skip if pixel hasn't changed
        if x_int == self.hover_x and y_int == self.hover_y and self.magnifier_active:
            return

        hdr = self.hdr_images[self.current_image_idx]

        if not (0 <= y_int < hdr.shape[0] and 0 <= x_int < hdr.shape[1]):
            if self.magnifier_active:
                self.magnifier_ax.set_visible(False)
                self.magnifier_active = False
                self.fig.canvas.draw_idle()
            return

        self.hover_x = x_int
        self.hover_y = y_int

        self.update_magnifier(x_int, y_int)
        
        # Highlight the histogram band for this pixel's luminance value
        self.highlight_histogram_band(x_int, y_int, hdr)

    def highlight_histogram_band(self, x, y, hdr):
        """
        Highlight the histogram band corresponding to the pixel's luminance value.
        """
        if self.histogram_bins is None or not self.hdr_images:
            return
        
        # Calculate luminance for this pixel
        pixel_r = hdr[y, x, 0]
        pixel_g = hdr[y, x, 1]
        pixel_b = hdr[y, x, 2]
        luminance = 0.2126 * pixel_r + 0.7152 * pixel_g + 0.0722 * pixel_b
        
        # Find which bin this luminance value falls into
        bin_idx = np.searchsorted(self.histogram_bins, luminance, side='right') - 1
        
        # Reset previous highlight
        if self.histogram_highlighted_bar is not None:
            self.histogram_highlighted_bar.set_alpha(0.7)
            self.histogram_highlighted_bar.set_edgecolor('none')
        
        # Highlight the matching bar
        if 0 <= bin_idx < len(self.ax_hist.patches):
            self.histogram_highlighted_bar = self.ax_hist.patches[bin_idx]
            self.histogram_highlighted_bar.set_alpha(1.0)
            self.histogram_highlighted_bar.set_edgecolor('red')
            self.histogram_highlighted_bar.set_linewidth(2)
            self.fig.canvas.draw_idle()

    def update_magnifier(self, x, y):
        """Update the magnifying glass display"""
        if not self.hdr_images:
            return

        display = self.get_display_image()
        if display is None:
            return

        zoom_size = 20

        x_min = max(0, x - zoom_size)
        x_max = min(display.shape[1], x + zoom_size)
        y_min = max(0, y - zoom_size)
        y_max = min(display.shape[0], y + zoom_size)

        zoomed = display[y_min:y_max, x_min:x_max]

        cmap_to_use = self.colormap
        norm = None
        if self.channel_mode == 'Luminance':
            if self.use_log_scale and self.log_vmin is not None and self.log_vmax is not None:
                norm = LogNorm(vmin=self.log_vmin, vmax=self.log_vmax)
                zoomed = np.where(zoomed < self.log_vmin, self.log_vmin, zoomed)
                vmin, vmax = None, None
            elif self.manual_vmin is not None and self.manual_vmax is not None:
                vmin = self.manual_vmin
                vmax = self.manual_vmax
            else:
                vmin = 0
                vmax = np.nanmax(display) * self.luminance_scale_factor
        else:
            vmin = 0
            vmax = 1

            if self.channel_mode == 'R':
                cmap_to_use = self.cmap_red
            elif self.channel_mode == 'G':
                cmap_to_use = self.cmap_green
            elif self.channel_mode == 'B':
                cmap_to_use = self.cmap_blue

        self.magnifier_ax.clear()
        if norm is not None:
            self.magnifier_ax.imshow(zoomed, cmap=cmap_to_use, interpolation='nearest', norm=norm)
        else:
            self.magnifier_ax.imshow(zoomed, cmap=cmap_to_use, interpolation='nearest',
                                     vmin=vmin, vmax=vmax)

        center_x = x - x_min
        center_y = y - y_min
        self.magnifier_ax.axhline(center_y, color='red', linewidth=1, alpha=0.7)
        self.magnifier_ax.axvline(center_x, color='red', linewidth=1, alpha=0.7)

        pixel_value = display[y, x]
        self.magnifier_ax.set_title(f'[{x}, {y}]: {self._fmt_lum(pixel_value)} cd/m²', 
                                   fontsize=8, pad=2)

        self.magnifier_ax.set_xticks([])
        self.magnifier_ax.set_yticks([])

        if not self.magnifier_active:
            self.magnifier_ax.set_visible(True)
            self.magnifier_active = True

        self.fig.canvas.draw_idle()

    def on_histogram_click(self, event):
        """
        Handle double-click on histogram axes to toggle axis lock.
        Double-click near the X axis (bottom strip) to toggle X lock.
        Double-click near the Y axis (left strip) to toggle Y lock.
        """
        if not event.dblclick or event.inaxes != self.ax_hist:
            return
        # Check if click is in bottom 15% of y-range (near X axis)
        y_lim = event.inaxes.get_ylim()
        y_range = y_lim[1] - y_lim[0]
        y_pos = event.ydata
        if (y_pos - y_lim[0]) < (0.15 * y_range):
            self.histogram_x_locked = not self.histogram_x_locked
            print(f"Histogram X-axis {'LOCKED' if self.histogram_x_locked else 'UNLOCKED'}")
        else:
            # Otherwise toggle Y-axis lock
            self.histogram_y_locked = not self.histogram_y_locked
            print(f"Histogram Y-axis {'LOCKED' if self.histogram_y_locked else 'UNLOCKED'}")
        self.update_histogram()
        self.fig.canvas.draw_idle()

    def on_histogram_hover(self, event):
        """
        Handle mouse hover over histogram to show actual bar count feedback.
        """
        if event.inaxes != self.ax_hist or self.histogram_bins is None:
            # Remove hover text if mouse leaves histogram or no data
            if self.histogram_hover_text is not None:
                self.histogram_hover_text.remove()
                self.histogram_hover_text = None
            if self.histogram_highlighted_bar is not None:
                self.histogram_highlighted_bar.set_alpha(0.7)
                self.histogram_highlighted_bar = None
            self.fig.canvas.draw_idle()
            return

        x = event.xdata
        if x is None:
            if self.histogram_hover_text is not None:
                self.histogram_hover_text.remove()
                self.histogram_hover_text = None
            self.fig.canvas.draw_idle()
            return

        # Find which bin the x position falls into
        bin_idx = np.searchsorted(self.histogram_bins, x, side='right') - 1
        if bin_idx < 0 or bin_idx >= len(self.histogram_counts):
            if self.histogram_hover_text is not None:
                self.histogram_hover_text.remove()
                self.histogram_hover_text = None
            self.fig.canvas.draw_idle()
            return
        
        # Get the actual count for this bin
        count = self.histogram_counts[bin_idx]
        bin_center = (self.histogram_bins[bin_idx] + self.histogram_bins[bin_idx + 1]) / 2

        # Remove old hover text
        if self.histogram_hover_text is not None:
            self.histogram_hover_text.remove()
        
        # Highlight the bar
        patches = self.ax_hist.patches
        if self.histogram_highlighted_bar is not None:
            self.histogram_highlighted_bar.set_alpha(0.7)
        if bin_idx < len(patches):
            self.histogram_highlighted_bar = patches[bin_idx]
            self.histogram_highlighted_bar.set_alpha(1.0)

        # Create new hover text with the actual bar count
        hover_text = f"X: {bin_center:.2e}\nCount: {count:.0f}"
        self.histogram_hover_text = self.ax_hist.text(
            0.98, 0.98, hover_text,
            transform=self.ax_hist.transAxes,
            fontsize=9,
            verticalalignment='top',
            horizontalalignment='right',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.7),
            fontfamily='monospace'
        )
        self.fig.canvas.draw_idle()

    def update_exposure(self, val):
        """Update exposure value"""
        self.exposure = val
        self.update_display()

    def update_gamma(self, val):
        """Update gamma value"""
        self.gamma = val
        self.update_display()

    def update_luminance_scale(self, val):
        """Update luminance scale factor"""
        self.luminance_scale_factor = val
        if self.channel_mode == 'Luminance':
            self.update_display()

    def update_white_threshold(self, val):
        """Update white threshold for dominant color mode"""
        self.white_threshold = val
        if self.channel_mode == 'Dominant Color':
            self.ldr_cache = None
            self.ldr_cache_key = None
            self.update_display()

    def update_r_threshold(self, val):
        """Update red channel threshold for dominant color mode"""
        self.dominant_color_r_threshold = val
        self._update_threshold_displays()
        if self.channel_mode == 'Dominant Color':
            self.ldr_cache = None
            self.ldr_cache_key = None
            self.update_display()

    def update_g_threshold(self, val):
        """Update green channel threshold for dominant color mode"""
        self.dominant_color_g_threshold = val
        self._update_threshold_displays()
        if self.channel_mode == 'Dominant Color':
            self.ldr_cache = None
            self.ldr_cache_key = None
            self.update_display()

    def update_b_threshold(self, val):
        """Update blue channel threshold for dominant color mode"""
        self.dominant_color_b_threshold = val
        self._update_threshold_displays()
        if self.channel_mode == 'Dominant Color':
            self.ldr_cache = None
            self.ldr_cache_key = None
            self.update_display()

    def _update_threshold_displays(self):
        """Update numeric displays for threshold values"""
        self._r_threshold_text.set_text(f'{self.dominant_color_r_threshold:.2f}')
        self._g_threshold_text.set_text(f'{self.dominant_color_g_threshold:.2f}')
        self._b_threshold_text.set_text(f'{self.dominant_color_b_threshold:.2f}')
        self.fig.canvas.draw_idle()

    def next_image(self, event):
        """Show next image (within current sensor filter)"""
        if self.hdr_images:
            filtered = self._get_filtered_indices()
            if not filtered:
                return
            if self.current_image_idx in filtered:
                pos = filtered.index(self.current_image_idx)
                self.current_image_idx = filtered[(pos + 1) % len(filtered)]
            else:
                self.current_image_idx = filtered[0]

            self.luminance_cache = None
            self.luminance_cache_idx = -1
            self.hdr_stats_cache = None
            self.hdr_stats_cache_idx = -1
            self.update_display()

    def previous_image(self, event):
        """Show previous image (within current sensor filter)"""
        if self.hdr_images:
            filtered = self._get_filtered_indices()
            if not filtered:
                return
            if self.current_image_idx in filtered:
                pos = filtered.index(self.current_image_idx)
                self.current_image_idx = filtered[(pos - 1) % len(filtered)]
            else:
                self.current_image_idx = filtered[-1]

            self.luminance_cache = None
            self.luminance_cache_idx = -1
            self.hdr_stats_cache = None
            self.hdr_stats_cache_idx = -1
            self.update_display()

    def toggle_false_color(self, event):
        """Toggle false color visualization"""
        self.show_false_color = not self.show_false_color
        self.update_display()

    def toggle_saturation(self, event):
        """Toggle saturation overlay"""
        self.show_saturation = not self.show_saturation
        self.update_display()

    def toggle_log_scale(self, event):
        """Toggle log-scale normalization for luminance and false-color views"""
        self.use_log_scale = not self.use_log_scale
        self.btn_log_scale.label.set_text('Log Scale: ON' if self.use_log_scale else 'Log Scale: OFF')
        self.update_display()

    def change_channel(self, label):
        """Change the channel display mode"""
        self.channel_mode = label

        # Show/hide dominant color sliders only when in Dominant Color mode
        is_dominant_color = (label == 'Dominant Color')
        self.slider_white_threshold.ax.set_visible(is_dominant_color)
        self.slider_r_threshold.ax.set_visible(is_dominant_color)
        self.slider_g_threshold.ax.set_visible(is_dominant_color)
        self.slider_b_threshold.ax.set_visible(is_dominant_color)
        self._r_threshold_text.set_visible(is_dominant_color)
        self._g_threshold_text.set_visible(is_dominant_color)
        self._b_threshold_text.set_visible(is_dominant_color)
        
        # Update threshold text displays
        if is_dominant_color:
            self._update_threshold_displays()

        if label not in ['Luminance', 'Dominant Color']:
            self.luminance_stats = None
            self.illuminance_lux = None
            self.luminance_cache = None
            self.luminance_cache_idx = -1

            if self.magnifier_active:
                self.magnifier_ax.set_visible(False)
                self.magnifier_active = False
        self.update_display()

    def calculate_luminance_stats(self, luminance):
        """Calculate and cache luminance statistics and illuminance"""
        valid_luminance = luminance[~np.isnan(luminance) & ~np.isinf(luminance)]
        if len(valid_luminance) > 0:
            self.luminance_stats = {
                'mean': float(np.mean(valid_luminance)),
                'median': float(np.median(valid_luminance)),
                'min': float(np.min(valid_luminance)),
                'max': float(np.max(valid_luminance)),
                'std': float(np.std(valid_luminance)),
                'count': len(valid_luminance)
            }

            if self.roi_params is not None:
                try:
                    self.illuminance_lux = self.calculate_illuminance(luminance)
                    print(f"Calculated illuminance: {self.illuminance_lux:.2f} lux")
                except Exception as e:
                    print(f"Warning: Could not calculate illuminance: {e}")
                    import traceback
                    traceback.print_exc()
                    self.illuminance_lux = None
            else:
                self.illuminance_lux = None
                print("Illuminance not calculated (no ROI params)")
        else:
            self.luminance_stats = None
            self.illuminance_lux = None

    def set_manual_limits(self):
        """Open dialog to set manual colorbar limits"""
        import tkinter as tk
        from tkinter import simpledialog

        if not self.hdr_images:
            return

        if self.manual_vmin is not None and self.manual_vmax is not None:
            current_min = self.manual_vmin
            current_max = self.manual_vmax
        else:

            display = self.get_display_image()
            if display is not None:
                current_min = display.min()
                current_max = display.max()
            else:
                current_min = 0
                current_max = 1

        root = tk.Tk()
        root.withdraw()

        min_val = simpledialog.askfloat(
            "Set Colorbar Limits",
            f"Enter minimum value (current: {current_min:.4f}):",
            initialvalue=current_min
        )

        if min_val is None:
            root.destroy()
            return

        max_val = simpledialog.askfloat(
            "Set Colorbar Limits",
            f"Enter maximum value (current: {current_max:.4f}):",
            initialvalue=current_max
        )

        if max_val is None:
            root.destroy()
            return

        root.destroy()

        if min_val < max_val:
            self.manual_vmin = min_val
            self.manual_vmax = max_val
            self.update_display()
            print(f"Colorbar limits set to: [{min_val:.4f}, {max_val:.4f}]")
        else:
            print("Error: Min value must be less than max value")

    def reset_manual_limits(self, event):
        """Reset manual colorbar limits to auto"""
        self.manual_vmin = None
        self.manual_vmax = None
        self.update_display()
        print("Colorbar limits reset to auto")

    def clear_clicks(self, event):
        """Clear all click markers"""
        self.click_markers = []
        self.update_display()
        print("Click markers cleared")

    def clear_images(self, event):
        """Remove all loaded images and reset viewer state"""
        self.hdr_images = []
        self.hdr_names = []
        self.hdr_metadata = []
        self.current_image_idx = 0
        self.current_hdr_path = None
        self.click_markers = []
        self.luminance_cache = None
        self.luminance_cache_idx = -1
        self.luminance_stats = None
        self.illuminance_lux = None
        self.saturation_mask = None
        self.saturation_count = 0
        self.saturation_percentage = 0.0
        self.saturation_roi_overlap = False
        self.roi_params = None
        self.ldr_cache = None
        self.ldr_cache_key = None
        self.hdr_stats_cache = None
        self.hdr_stats_cache_idx = -1
        self.manual_vmin = None
        self.manual_vmax = None
        self.hover_x = None
        self.hover_y = None
        self.magnifier_active = False
        self.magnifier_ax.set_visible(False)
        self.sensor_filter = None
        self.update_sensor_buttons()
        self.update_display()
        print("All images cleared")

    @staticmethod
    def _get_sensor_name(filename):
        """Extract sensor ID from filename (last underscore-delimited part before extension).
        E.g. '20260406_113000_sensor12.hdr' -> 'sensor12'
        """
        stem = os.path.splitext(filename)[0]
        parts = stem.split('_')
        return parts[-1] if parts else stem

    def _get_visible_sensors(self):
        """Return sorted list of unique sensor names from all loaded images."""
        seen = set()
        sensors = []
        for name in self.hdr_names:
            s = self._get_sensor_name(name)
            if s not in seen:
                seen.add(s)
                sensors.append(s)
        sensors.sort()
        return sensors

    def _get_filtered_indices(self):
        """Return list of image indices matching the current sensor filter (all if filter is None)."""
        if self.sensor_filter is None:
            return list(range(len(self.hdr_images)))
        return [i for i, name in enumerate(self.hdr_names)
                if self._get_sensor_name(name) == self.sensor_filter]

    def update_sensor_buttons(self):
        """Show/hide and label sensor filter buttons based on loaded images."""
        sensors = self._get_visible_sensors()
        has_multiple = len(sensors) > 1

        self._filter_label_text.set_visible(has_multiple)
        self._filter_btn_all_ax.set_visible(has_multiple)

        for i, (ax, btn) in enumerate(zip(self._filter_btn_axes, self._filter_btns)):
            if has_multiple and i < len(sensors):
                btn.label.set_text(sensors[i])
                ax.set_visible(True)
            else:
                ax.set_visible(False)

        self._update_filter_highlight()
        self.fig.canvas.draw_idle()

    def _update_filter_highlight(self):
        """Update button background colors to reflect the active filter."""
        ACTIVE_COLOR = '#4a90d9'
        INACTIVE_COLOR = '0.85'

        is_all = self.sensor_filter is None
        self._filter_btn_all.color = ACTIVE_COLOR if is_all else INACTIVE_COLOR
        self._filter_btn_all_ax.set_facecolor(ACTIVE_COLOR if is_all else INACTIVE_COLOR)

        sensors = self._get_visible_sensors()
        for i, (ax, btn) in enumerate(zip(self._filter_btn_axes, self._filter_btns)):
            if i < len(sensors):
                is_active = (self.sensor_filter == sensors[i])
                btn.color = ACTIVE_COLOR if is_active else INACTIVE_COLOR
                ax.set_facecolor(ACTIVE_COLOR if is_active else INACTIVE_COLOR)

    def _on_filter_all(self, event):
        """Handle 'All' filter button: clear sensor filter and refresh display."""
        self.sensor_filter = None
        self._update_filter_highlight()
        self.update_display()

    def _make_sensor_handler(self, idx):
        """Create a click handler for the sensor button at position idx."""
        def handler(event):
            sensors = self._get_visible_sensors()
            if idx >= len(sensors):
                return
            sensor = sensors[idx]
            if self.sensor_filter == sensor:
                self.sensor_filter = None  # toggle off
            else:
                self.sensor_filter = sensor
                filtered = self._get_filtered_indices()
                if filtered and self.current_image_idx not in filtered:
                    self.current_image_idx = filtered[0]
                    self.luminance_cache = None
                    self.luminance_cache_idx = -1
                    self.hdr_stats_cache = None
                    self.hdr_stats_cache_idx = -1
            self._update_filter_highlight()
            self.update_display()
        return handler

    def _default_save_name(self, suffix=''):
        """Build default save filename from the loaded HDR name + channel suffix."""
        if self.hdr_images:
            base = os.path.splitext(self.hdr_names[self.current_image_idx])[0]
        else:
            base = 'hdr_view'
        channel_tag = self.channel_mode.replace(' ', '_')
        return f"{base}_{channel_tag}{suffix}.png"

    def save_figure(self, event):
        """Save the current figure view to PNG"""
        import tkinter as tk
        from tkinter import filedialog

        if not self.hdr_images:
            print("No image to save")
            return

        try:
            root = tk.Tk()
            root.withdraw()

            default_name = self._default_save_name('_view')

            filepath = filedialog.asksaveasfilename(
                title='Save figure as PNG',
                defaultextension='.png',
                initialfile=default_name,
                filetypes=[('PNG files', '*.png'), ('All files', '*.*')]
            )

            root.destroy()

            if filepath:

                self.fig.savefig(filepath, dpi=self.SAVE_DPI, bbox_inches='tight', facecolor='white')
                print(f"Figure saved to: {filepath}")
        except Exception as e:
            print(f"Error saving figure: {e}")
            import traceback
            traceback.print_exc()

    def save_image_only(self, event):
        """Save only the fisheye image with colorbar on transparent background"""
        import tkinter as tk
        from tkinter import filedialog

        if not self.hdr_images:
            print("No image to save")
            return

        try:
            default_name = self._default_save_name()

            root = tk.Tk()
            root.withdraw()

            filepath = filedialog.asksaveasfilename(
                title='Save image only as PNG',
                defaultextension='.png',
                initialfile=default_name,
                filetypes=[('PNG files', '*.png'), ('All files', '*.*')]
            )

            root.destroy()

            if filepath:

                display = self.get_display_image()
                if display is None:
                    print("No image to save")
                    return

                needs_colorbar = False
                cmap_to_use = 'gray'
                vmin, vmax = 0, 1
                norm = None
                cbar_label = 'Intensity'

                if self.channel_mode == 'Luminance':
                    needs_colorbar = True
                    cmap_to_use = self.colormap
                    if self.use_log_scale:
                        pos_vals = display[display > 0]
                        log_vmin = max(self.manual_vmin, 1e-6) if self.manual_vmin is not None else (float(np.nanpercentile(pos_vals, 1)) if len(pos_vals) > 0 else 1e-6)
                        log_vmax = self.manual_vmax if self.manual_vmax is not None else float(np.nanmax(display)) * self.luminance_scale_factor
                        norm = LogNorm(vmin=log_vmin, vmax=max(log_vmax, log_vmin * 10))
                    elif self.manual_vmin is not None and self.manual_vmax is not None:
                        vmin = self.manual_vmin
                        vmax = self.manual_vmax
                    else:
                        vmin = 0
                        vmax = np.nanmax(display) * self.luminance_scale_factor
                    cbar_label = 'Luminance (cd/m²) [log]' if self.use_log_scale else 'Luminance (cd/m²)'
                elif self.show_false_color and len(display.shape) == 2:
                    needs_colorbar = True
                    cmap_to_use = self.colormap
                    if self.use_log_scale:
                        pos_vals = display[display > 0]
                        log_vmin = max(self.manual_vmin, 1e-6) if self.manual_vmin is not None else (float(np.nanpercentile(pos_vals, 1)) if len(pos_vals) > 0 else 1e-6)
                        log_vmax = self.manual_vmax if self.manual_vmax is not None else float(np.nanmax(display))
                        norm = LogNorm(vmin=log_vmin, vmax=max(log_vmax, log_vmin * 10))
                    elif self.manual_vmin is not None and self.manual_vmax is not None:
                        vmin = self.manual_vmin
                        vmax = self.manual_vmax
                    else:
                        vmin = display.min()
                        vmax = display.max()
                    cbar_label = 'Intensity [log]' if self.use_log_scale else 'Intensity'
                elif len(display.shape) == 2 and self.channel_mode in ['R', 'G', 'B']:
                    needs_colorbar = True
                    if self.channel_mode == 'R':
                        cmap_to_use = self.cmap_red
                        cbar_label = 'Red Channel'
                    elif self.channel_mode == 'G':
                        cmap_to_use = self.cmap_green
                        cbar_label = 'Green Channel'
                    elif self.channel_mode == 'B':
                        cmap_to_use = self.cmap_blue
                        cbar_label = 'Blue Channel'
                    vmin = 0
                    vmax = 1
                elif len(display.shape) == 2 and self.channel_mode == 'Gray':
                    needs_colorbar = True
                    cmap_to_use = 'gray'
                    vmin = 0
                    vmax = 1
                    cbar_label = 'Grayscale'

                if needs_colorbar:
                    fig_temp = plt.figure(figsize=(10, 10))
                    ax_temp = fig_temp.add_axes([0.1, 0.1, 0.75, 0.8])
                else:
                    fig_temp = plt.figure(figsize=(10, 10))
                    ax_temp = fig_temp.add_axes([0.1, 0.1, 0.8, 0.8])

                if len(display.shape) == 2:
                    if norm is not None:
                        im = ax_temp.imshow(display, cmap=cmap_to_use, interpolation='nearest', norm=norm)
                    else:
                        im = ax_temp.imshow(display, cmap=cmap_to_use, interpolation='nearest', vmin=vmin, vmax=vmax)
                else:
                    im = ax_temp.imshow(display, interpolation='nearest')

                ax_temp.axis('off')

                if needs_colorbar:
                    cbar = fig_temp.colorbar(im, ax=ax_temp, fraction=0.046, pad=0.04)
                    cbar.set_label(cbar_label, rotation=270, labelpad=20)

                if self.channel_mode == 'Luminance' and self.click_markers:
                    for x, y, lum_val in self.click_markers:
                        ax_temp.plot(x, y, 'r+', markersize=15, markeredgewidth=2)
                        ax_temp.text(x + 10, y - 10, f'{lum_val:.1f}', 
                                    color='red', fontsize=10, fontweight='bold',
                                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

                if self.show_saturation and self.saturation_mask is not None:
                    ax_temp.contour(self.saturation_mask.astype(float), 
                                  levels=[0.5], 
                                  colors=['#FF00FF'],
                                  linewidths=2.0,
                                  linestyles='solid')

                fig_temp.savefig(filepath, dpi=self.SAVE_DPI, bbox_inches='tight', 
                               transparent=True, facecolor='none')
                plt.close(fig_temp)

                print(f"Image ({self.channel_mode} channel) saved to: {filepath}")
        except Exception as e:
            print(f"Error saving image: {e}")
            import traceback
            traceback.print_exc()

    def ask_sensor_id(self):
        """Ask user to manually enter sensor ID"""
        try:
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()

            sensor_id = simpledialog.askstring(
                "Sensor ID Required",
                "Enter sensor ID for illuminance calculation\n(e.g., sensor11, sensor05)\n\nLeave empty to skip:",
                initialvalue="sensor11"
            )

            root.destroy()

            if sensor_id:
                sensor_id = sensor_id.lower().strip()
                if not sensor_id.startswith('sensor'):
                    print(f"Warning: Sensor ID '{sensor_id}' doesn't start with 'sensor'")
                return sensor_id
            return None
        except Exception as e:
            print(f"Error asking for sensor ID: {e}")
            return None

    def try_load_roi_params(self, hdr_filepath):
        """Try to load ROI parameters from roi_params.json or HDR header calibration data."""
        try:
            filename = os.path.basename(hdr_filepath)
            import re
            match = re.search(r'sensor\d+', filename, re.IGNORECASE)
            sensor_id = None

            meta = self.hdr_metadata[-1] if self.hdr_metadata else {}

            if match:
                sensor_id = match.group(0).lower()
                print(f"Detected sensor ID from filename: {sensor_id}")
            elif meta.get('DEVICE'):
                device_match = re.search(r'sensor\d+', meta['DEVICE'], re.IGNORECASE)
                sensor_id = device_match.group(0).lower() if device_match else meta['DEVICE'].lower()
                print(f"Detected sensor ID from DEVICE header: {sensor_id}")
            else:
                print(f"No sensor ID found in filename: {filename}")
                sensor_id = self.ask_sensor_id()

            roi_loaded = False

            if sensor_id:
                current_path = Path(hdr_filepath).parent
                workspace = current_path
                roi_path = None
                search_depth = 0
                while workspace.parent != workspace and search_depth < 10:
                    test_paths = [
                        workspace / '01_define_roi_output' / 'roi_params.json',
                        workspace / '02_calibration_input' / 'roi_params.json'
                    ]
                    for test_path in test_paths:
                        if test_path.exists():
                            roi_path = test_path
                            break
                    if roi_path:
                        break
                    workspace = workspace.parent
                    search_depth += 1

                if roi_path:
                    print(f"Found ROI params file: {roi_path}")
                    with open(roi_path, 'r') as f:
                        roi_data = json.load(f)

                    if sensor_id in roi_data:
                        self.roi_params = roi_data[sensor_id]
                        self.roi_params['_source'] = 'file'
                        print(f"✓ Loaded ROI params for {sensor_id} from file")
                        print(f"  Center: ({self.roi_params['center_x']}, {self.roi_params['center_y']})")
                        print(f"  Radius: ({self.roi_params['radius_x']}, {self.roi_params['radius_y']})")
                        roi_loaded = True
                    else:
                        available = list(roi_data.keys())
                        print(f"Sensor '{sensor_id}' not found in ROI params file.")
                        print(f"Available sensors: {', '.join(available)}")
                else:
                    print(f"ROI parameters file not found.")

            # Fall back to header-embedded calibration data
            if not roi_loaded:
                if meta.get('CAL_VIGN_CENTER') and meta.get('CAL_VIGN_MAXDIST'):
                    try:
                        cx, cy = map(float, meta['CAL_VIGN_CENTER'].split())
                        r = float(meta['CAL_VIGN_MAXDIST'])
                        self.roi_params = {
                            'center_x': cx,
                            'center_y': cy,
                            'radius_x': r,
                            'radius_y': r,
                            '_source': 'header',
                        }
                        print(f"✓ Loaded ROI from HDR header (CAL_VIGN_CENTER/MAXDIST)")
                        print(f"  Center: ({cx:.1f}, {cy:.1f}), Radius: {r:.1f}")
                        roi_loaded = True
                    except Exception as e:
                        print(f"Warning: could not parse header ROI data: {e}")

            if not roi_loaded:
                print("ROI parameters not available. Illuminance calculation disabled.")
                self.roi_params = None

        except Exception as e:
            print(f"Error loading ROI params: {e}")
            import traceback
            traceback.print_exc()
            self.roi_params = None

    def find_response_file(self, hdr_filepath):
        """Find and load the corresponding response file for the HDR image"""
        try:
            hdr_path = Path(hdr_filepath)

            base_name = hdr_path.stem

            workspace = hdr_path.parent
            search_dirs = [hdr_path.parent] 

            search_depth = 0
            while workspace.parent != workspace and search_depth < 10:
                test_path = workspace / '02_generate_response_output'
                if test_path.exists():
                    search_dirs.append(test_path)
                workspace = workspace.parent
                search_depth += 1

            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue

                for rsp_file in search_dir.glob(f"*{base_name}*.rsp"):
                    print(f"Found response file: {rsp_file}")
                    return self.parse_response_file(rsp_file)

                for rsp_file in search_dir.glob("*.rsp"):
                    if base_name in rsp_file.stem or rsp_file.stem in base_name:
                        print(f"Found response file: {rsp_file}")
                        return self.parse_response_file(rsp_file)

            print(f"No response file found for {hdr_filepath}")
            return None
        except Exception as e:
            print(f"Error finding response file: {e}")
            return None

    def parse_response_file(self, rsp_filepath):
        """Parse response file to extract exposure times and image paths"""
        try:
            exposures = []
            with open(rsp_filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        exposure_time = float(parts[0])
                        image_path = parts[1]
                        exposures.append((exposure_time, image_path))

            if not exposures:
                print("No exposures found in response file")
                return None

            exposures.sort(key=lambda x: x[0])
            shortest_exposure = exposures[0]
            print(f"Shortest exposure: {shortest_exposure[0]}s -> {shortest_exposure[1]}")

            return {
                'shortest_exposure_time': shortest_exposure[0],
                'shortest_exposure_path': shortest_exposure[1],
                'all_exposures': exposures
            }
        except Exception as e:
            print(f"Error parsing response file: {e}")
            return None

    def load_saturation_data(self, hdr_filepath):
        """Load saturation data from the shortest exposure image"""
        try:

            response_info = self.find_response_file(hdr_filepath)
            if response_info is None:
                print("Cannot load saturation data: no response file found")
                self.saturation_mask = None 
                return

            shortest_path = response_info['shortest_exposure_path']

            if not os.path.isabs(shortest_path):

                hdr_dir = Path(hdr_filepath).parent
                possible_paths = [
                    hdr_dir / shortest_path,
                    hdr_dir.parent / '01_define_roi_input' / shortest_path,
                    Path(shortest_path)
                ]

                shortest_path = None
                for path in possible_paths:
                    if path.exists():
                        shortest_path = str(path)
                        break

                if shortest_path is None:
                    print("Cannot find shortest exposure image")
                    self.saturation_mask = None
                    return

            img = cv2.imread(shortest_path, cv2.IMREAD_COLOR)
            if img is None:
                print(f"Cannot load image: {shortest_path}")
                self.saturation_mask = None
                return

            print(f"Loaded shortest exposure image: {shortest_path}")

            saturation_threshold = 250
            mask = np.any(img > saturation_threshold, axis=2)

            self.saturation_mask = mask
            self.saturation_count = np.sum(mask)
            total_pixels = mask.shape[0] * mask.shape[1]
            self.saturation_percentage = (self.saturation_count / total_pixels) * 100

            self.saturation_roi_overlap = False
            if self.roi_params is not None and self.saturation_count > 0:
                height, width = mask.shape
                center_x = self.roi_params['center_x']
                center_y = self.roi_params['center_y']
                radius_x = self.roi_params['radius_x']
                radius_y = self.roi_params['radius_y']

                y_coords, x_coords = np.mgrid[0:height, 0:width]
                dx = (x_coords - center_x) / radius_x
                dy = (y_coords - center_y) / radius_y
                roi_mask = (dx**2 + dy**2) <= 1.0

                overlap = np.any(mask & roi_mask)
                self.saturation_roi_overlap = overlap

            print(f"Saturation: {self.saturation_count:,} pixels ({self.saturation_percentage:.2f}%)")
            if self.saturation_roi_overlap:
                print("⚠️ Warning: ROI contains saturated pixels!")

        except Exception as e:
            print(f"Error loading saturation data: {e}")
            import traceback
            traceback.print_exc()
            self.saturation_mask = None

    def calculate_illuminance(self, luminance_map):
        """Calculate horizontal illuminance from luminance map using fisheye geometry"""
        if self.roi_params is None:
            return None

        height, width = luminance_map.shape
        center_x = self.roi_params['center_x']
        center_y = self.roi_params['center_y']
        radius = (self.roi_params['radius_x'] + self.roi_params['radius_y']) / 2
        fov_degrees = 161 

        y_coords, x_coords = np.mgrid[0:height, 0:width]
        dx = x_coords - center_x
        dy = y_coords - center_y
        r_pixels = np.sqrt(dx**2 + dy**2)
        valid_mask = r_pixels <= radius

        fov_radians = np.deg2rad(fov_degrees)
        max_angle = fov_radians / 2.0
        focal_length = radius / max_angle
        zenith_angles = r_pixels / focal_length
        zenith_angles = np.clip(zenith_angles, 0, max_angle)
        zenith_angles[~valid_mask] = np.nan
        delta_theta = fov_radians / radius
        delta_phi = 2 * np.pi / (2 * np.pi * radius)
        pixel_solid_angle_base = delta_theta * delta_phi
        solid_angle = np.sin(zenith_angles) * pixel_solid_angle_base
        cos_theta = np.cos(zenith_angles)
        valid_luminance = luminance_map[valid_mask]
        valid_cos = cos_theta[valid_mask]
        valid_solid_angle = solid_angle[valid_mask]

        valid_data = ~(np.isnan(valid_luminance) | np.isnan(valid_cos) | np.isnan(valid_solid_angle))
        illuminance = np.sum(
            valid_luminance[valid_data] * 
            valid_cos[valid_data] * 
            valid_solid_angle[valid_data]
        )

        return float(illuminance)

    def show(self):
        """Display the viewer"""
        plt.show()

def main():
    """Main function to run the HDR viewer application."""
    import sys

    viewer = HDRViewer()

    if len(sys.argv) > 1:
        for filepath in sys.argv[1:]:
            if not os.path.exists(filepath):
                print(f"File not found: {filepath}")
            elif tarfile.is_tarfile(filepath):
                viewer.load_tar(filepath)
            else:
                viewer.load_hdr(filepath)

    print("\n" + "="*60)
    print("HDR VIEWER - Instructions")
    print("="*60)
    print("• Use 'Load HDR' button to load HDR/EXR files")
    print("• Adjust 'Exposure' slider to change brightness (-5 to +5 EV)")
    print("• Adjust 'Gamma' slider for gamma correction (0.5 to 3.0)")
    print("• Adjust 'Lum Scale' slider to scale luminance display (5%-100%)")
    print("• Click on image pixels to see their values in console")
    print("• Use 'Prev'/'Next' buttons to navigate multiple images")
    print("• Use 'False Color' button to toggle heatmap visualization")
    print("• Select channel mode (RGB, R, G, B, Gray, Luminance) with radio buttons")
    print("• Use 'Luminance' mode to view photometric values in cd/m²")
    print("• Close window to exit")
    print("="*60 + "\n")

    viewer.show()

if __name__ == '__main__':
    main()