import os
import zarr
from tqdm import tqdm
import numpy as np
import tifffile as tiff
from tifffile import TiffFile
import shutil
from waveorder.io.writer import WaveorderWriter
from recOrder.preproc.pre_processing import get_autocontrast_limits
from xml.etree import ElementTree as etree
import glob

#TODO: Drop MM Dependency altogether?
class ZarrConverter:

    def __init__(self, data_directory, save_directory, save_name=None, append_position_names=False):

        # Init File IO Properties
        self.version = 'recOrder Converter version=0.2'
        self.data_directory = data_directory
        self.save_directory = save_directory
        self.files = glob.glob(os.path.join(self.data_directory, '*.ome.tif'))
        self.summary_metadata = self._generate_summary_metadata()
        self.data_name = self.summary_metadata['Prefix']
        self.save_name = self.data_name if not save_name else save_name
        self.append_position_names = append_position_names
        self.array = None
        self.zarr_store = None
        self.coord_map = dict()

        # Generate Data Specific Properties
        self.coords = None
        self.dim_order = None
        self.p_dim = None
        self.t_dim = None
        self.c_dim = None
        self.z_dim = None
        self.dtype = self._get_dtype()
        self.p = self.summary_metadata['IntendedDimensions']['position']
        self.t = self.summary_metadata['IntendedDimensions']['time']
        self.c = self.summary_metadata['IntendedDimensions']['channel']
        self.z = self.summary_metadata['IntendedDimensions']['z']
        self.y = self.summary_metadata['Height']
        self.x = self.summary_metadata['Width']
        self.dim = (self.p, self.t, self.c, self.z, self.y, self.x)
        self.focus_z = self.z // 2
        self.prefix_list = []
        print(f'Found Dataset {self.data_name} w/ dimensions (P, T, C, Z, Y, X): {self.dim}')

        # Initialize Metadata Dictionary
        self.metadata = dict()
        self.metadata['recOrder_Converter_Version'] = self.version
        self.metadata['Summary'] = self.summary_metadata

        # Initialize writer
        self.writer = WaveorderWriter(self.save_directory, datatype='raw', silence=True)
        self.writer.create_zarr_root(self.save_name)

    def _gen_coordset(self):
        """
        generates a coordinate set in the dimensional order to which the data was acquired.
        This is important for keeping track of where we are in the tiff file during conversion

        Returns
        -------
        list(tuples) w/ length [N_images]

        """

        # 4 possible dimensions: p, c, t, z
        n_dim = 4
        hashmap = {'position': self.p,
                   'time': self.t,
                   'channel': self.c,
                   'z': self.z}

        self.dim_order = self.summary_metadata['AxisOrder']

        dims = []
        for i in range(n_dim):
            if i < len(self.dim_order):
                dims.append(hashmap[self.dim_order[i]])
            else:
                dims.append(1)

        # Reverse the dimension order for easier calling later
        self.dim_order.reverse()

        # return array of coordinate tuples with innermost dimension being the first dim acquired
        return [(dim3, dim2, dim1, dim0) for dim3 in range(dims[3]) for dim2 in range(dims[2])
                for dim1 in range(dims[1]) for dim0 in range(dims[0])]

    def _gather_index_maps(self):
        """
        Will return a dictionary of {coord: (filepath, page)} of length(N_Images) to later query

        Returns
        -------

        """

        self.p_dim = self.dim_order.index('position')
        self.t_dim = self.dim_order.index('time')
        self.c_dim = self.dim_order.index('channel')
        self.z_dim = self.dim_order.index('z')

        for file in self.files:
            tf = tiff.TiffFile(file)
            meta = tf.micromanager_metadata['IndexMap']

            for page in range(len(meta['Channels'])):
                coord = [0, 0, 0, 0]
                coord[self.p_dim] = meta['Position'][page]
                coord[self.t_dim] = meta['Frame'][page]
                coord[self.c_dim] = meta['Channel'][page]
                coord[self.z_dim] = meta['Slice'][page]

                self.coord_map[tuple(coord)] = (file, page)


    def _generate_summary_metadata(self):
        """
        generates the summary metadata by opening any file and loading the micromanager_metadata

        Returns
        -------
        summary_metadata:       (dict) MM Summary Metadata

        """

        tf = tiff.TiffFile(self.files[0])
        return tf.micromanager_metadata['Summary']

    def _generate_plane_metadata(self, tiff_file, page):
        """
        generates the img plane metadata by saving the MicroManagerMetadata written in the tiff tags.

        This image-plane data houses information of the config when the image was acquired.

        Parameters
        ----------
        tiff_file:          (TiffFile Object) Opened TiffFile Object

        Returns
        -------
        image_metadata:     (dict) Dictionary of the image-plane metadata

        """

        for tag in tiff_file.pages[page].tags.values():
            if tag.name == 'MicroManagerMetadata':
                return tag.value
            else:
                continue

    def _get_dtype(self):
        """
        gets the datatype from the raw data array

        Returns
        -------

        """

        tf = tiff.TiffFile(self.files[0])
        image_data = self._generate_plane_metadata(tf, 0)
        bit_depth = image_data['BitDepth']

        dtype = f'uint{bit_depth}'

        return dtype

    def _preform_image_check(self, tiff_image, coord):
        """
        checks to make sure the memory mapped image matches the saved zarr image to ensure
        a successful conversion.

        Parameters
        ----------
        tiff_image:     (nd-array) memory mapped array
        coord:          (tuple) coordinate of the image location

        Returns
        -------
        True/False:     (bool) True if arrays are equal, false otherwise

        """

        zarr_array = self.writer.store[self.writer.get_current_group()]['raw_data']['array']
        zarr_img = zarr_array[coord[self.dim_order.index('time')],
                              coord[self.dim_order.index('channel')],
                              coord[self.dim_order.index('z')]]

        return np.array_equal(zarr_img, tiff_image)

    def _get_channel_names(self):
        """
        gets the chan names from the summary metadata (in order in which they were acquired)

        Returns
        -------

        """

        chan_names = self.metadata['Summary']['map']['ChNames']['array']

        return chan_names

    def _get_position_name(self, image_meta):

        return image_meta['map']['PositionName']['scalar'] if self.append_position_names else None

    def check_file_changed(self, last_file, current_file):
        """
        function to check whether or not the tiff file has changed.

        Parameters
        ----------
        last_file:          (str) filename of the last file looked at
        current_file:       (str) filename of the current file

        Returns
        -------
        True/False:       (bool) updated page number

        """

        if last_file != current_file or not last_file:
            return True
        else:
            return False

    def get_image_array(self, coord, opened_tiff):
        """
        Grabs the image array through memory mapping.  We must first find the byte offset which is located in the
        tiff page tag.  We then use that to quickly grab the bytes corresponding to the desired image.

        Parameters
        ----------
        data_file:          (str) path of the data-file to look at
        current_page:       (int) current tiff page

        Returns
        -------
        array:              (nd-array) image array of shape (Y, X)

        """
        file = coord[0]
        page = coord[1]

        # get byte offset from tiff tag metadata
        byte_offset = self.get_byte_offset(opened_tiff, page)

        array = np.memmap(file, dtype=self.dtype, mode='r', offset=byte_offset, shape=(self.y, self.x))

        return array

    # todo: update this func for new coordinate structure
    def get_channel_clims(self):
        """
        generate contrast limits for each channel.  Grabs the middle image of the stack to compute contrast limits
        Default clim is to ignore 1% of pixels on either end

        Returns
        -------
        clims:      [list]: list of tuples corresponding to the (min, max) contrast limits

        """

        clims = []
        for chan in range(self.c):
            img = self.get_image_object((0, 0, chan, self.focus_z))
            clims.append(get_autocontrast_limits(img.getRawPixels().reshape(self.y, self.x)))

        return clims

    def get_byte_offset(self, tiff_file, page):
        """
        Gets the byte offset from the tiff tag metadata

        Parameters
        ----------
        tiff_file:          (Tiff-File object) Opened tiff file
        page:               (int) Page to look at for the tag

        Returns
        -------
        byte offset:        (int) byte offset for the image array

        """

        for tag in tiff_file.pages[page].tags.values():
            if 'StripOffset' in tag.name:
                return tag.value[0]
            else:
                continue

    #TODO: get position names from summary metadata and update this function
    def init_zarr_structure(self):
        """
        Initiates the zarr store.  Will create a zarr store with user-specified name or original name of data
        if not provided.  Store will contain a group called 'array' with contains an array of original
        data dtype of dimensions (T, C, Z, Y, X).  Appends OME-zarr metadata with clims,chan_names

        Current compressor is Blosc zstd w/ bitshuffle (high compression, faster compression)

        Returns
        -------

        """

        clims = self.get_channel_clims()
        chan_names = self._get_channel_names()

        for pos in range(self.p):
            img = self.get_image_object((pos, 0, 0, 0))
            metadata = self._generate_plane_metadata(img)

            self.prefix_list.append(self._get_position_name(metadata))
            self.writer.create_position(pos, prefix=self.prefix_list[pos])
            self.writer.init_array(data_shape=(self.t if self.t != 0 else 1,
                                               self.c if self.c != 0 else 1,
                                               self.z if self.z != 0 else 1,
                                               self.y,
                                               self.x),
                                   chunk_size=(1, 1, 1, self.y, self.x),
                                   chan_names=chan_names,
                                   clims=clims,
                                   dtype=self.dtype)

    def run_conversion(self):
        """
        Runs the data conversion through memory mapping and performs an image check to make sure conversion did not
        alter any data values.

        Returns
        -------

        """

        # Run setup
        print('Running Conversion...')
        self._generate_summary_metadata()
        self.coords = self._gen_coordset()
        self.init_zarr_structure()
        self.writer.open_position(0, prefix=self.prefix_list[0])
        last_file = None

        #Format bar for CLI display
        bar_format = 'Status: |{bar}|{n_fmt}/{total_fmt} (Time Remaining: {remaining}), {rate_fmt}{postfix}]'

        # Run through every coordinate and convert image + grab image metadata, statistics
        for coord in tqdm(self.coords, bar_format=bar_format):

            # get the image object
            coord_reorder = [coord[self.dim_order.index('position')],
                             coord[self.dim_order.index('time')],
                             coord[self.dim_order.index('channel')],
                             coord[self.dim_order.index('z')]]

            # Only load tiff file if it has changed from previous run
            current_file = self.coord_map[coord][0]
            if self.check_file_changed(last_file, current_file):
                tf = tiff.TiffFile(current_file)

            # Get the metadata
            self.metadata['ImagePlaneMetadata'][f'{coord_reorder}'] = self._generate_plane_metadata(tf)

            # get the memory mapped image
            img_raw = self.get_image_array(self.coord_map[coord], tf)

            # Open the new position if the position index has changed
            if current_pos != coord[self.dim_order.index('position')]:
                self.writer.open_position(coord[self.dim_order.index('position')],
                                          prefix=self.prefix_list[coord[self.dim_order.index('position')]])
                current_pos = coord[self.dim_order.index('position')]

            # Write the data
            self.writer.write(img_raw, coord[self.dim_order.index('time')],
                              coord[self.dim_order.index('channel')],
                              coord[self.dim_order.index('z')])

            # Perform image check
            if not self._preform_image_check(img_raw, coord):
                raise ValueError('Converted zarr image does not match the raw data. Conversion Failed')

        # Put metadata into zarr store and cleanup
        self.writer.store.attrs.put(self.metadata)
        shutil.rmtree(self.temp_directory)













































