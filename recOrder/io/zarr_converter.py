import os
from tqdm import tqdm
import numpy as np
import tifffile as tiff
from waveorder.io.writer import WaveorderWriter
from waveorder.io.reader import WaveorderReader
from recOrder.preproc.pre_processing import get_autocontrast_limits
from recOrder.io.utils import create_grid_from_coordinates
import glob
import json
import warnings


#TODO: Make converter agnostic to metadata present (especially for upti)
class ZarrConverter:
    """
    This converter works to convert micromanager ome tiff or single-page tiff stacks into
    OME-HCS format zarr.  User can specify to fully-format in HCS, in which case it will
    lay out the positions in a grid-like format based on how the data was acquired (useful
    for tiled acquisitions)
    """

    def __init__(self, input, output, data_type, replace_position_names=False, format_hcs=False):

        # Add Initial Checks
        if len(glob.glob(os.path.join(input, '*.tif'))) == 0:
            raise ValueError('Specific input contains no .tif files, please specify a valid input directory')
        if not output.endswith('.zarr'):
            raise ValueError('Please specify .zarr at the end of your output')

        # ignore tiffile warnings
        warnings.filterwarnings('ignore')

        # Init File IO Properties
        self.version = 'recOrder Converter version=0.4'
        self.data_directory = input
        self.save_directory = os.path.dirname(output)
        self.files = glob.glob(os.path.join(self.data_directory, '*.tif'))
        self.data_type = data_type
        self.meta_file = None

        print('Initializing Data...')
        self.reader = WaveorderReader(self.data_directory, self.data_type, extract_data=True)
        print('Finished initializing data')

        self.summary_metadata = self.reader.mm_meta['Summary'] if self.reader.mm_meta else None
        self.save_name = os.path.basename(output)
        if self.data_type != 'upti':
            self.mfile_name = os.path.join(self.save_directory, f'{self.save_name.strip(".zarr")}_ImagePlaneMetadata.txt')
            self.meta_file = open(self.mfile_name, 'a')

        self.replace_position_names = replace_position_names
        self.format_hcs = format_hcs

        if not os.path.exists(self.save_directory):
            os.mkdir(self.save_directory)

        # Generate Data Specific Properties
        self.coords = None
        self.coord_map = dict()
        self.pos_names = []
        self.dim_order = None
        self.p_dim = None
        self.t_dim = None
        self.c_dim = None
        self.z_dim = None
        self.dtype = self.reader.reader.dtype
        self.p = self.reader.get_num_positions()
        self.t = self.reader.frames
        self.c = self.reader.channels
        self.z = self.reader.slices
        self.y = self.reader.height
        self.x = self.reader.width
        self.dim = (self.p, self.t, self.c, self.z, self.y, self.x)
        self.focus_z = self.z // 2
        self.prefix_list = []
        print(f'Found Dataset {self.save_name} w/ dimensions (P, T, C, Z, Y, X): {self.dim}')

        # Initialize Metadata Dictionary
        self.metadata = dict()
        self.metadata['recOrder_Converter_Version'] = self.version
        self.metadata['Summary'] = self.summary_metadata
        self.metadata['ImagePlaneMetadata'] = dict()

        # initialize metadata if HCS desired, init writer
        self.hcs_meta = self._generate_hcs_metadata() if self.format_hcs else None
        self.writer = WaveorderWriter(self.save_directory, hcs=self.format_hcs, hcs_meta=self.hcs_meta, verbose=False)
        self.writer.create_zarr_root(self.save_name)

    def _gather_index_maps(self):
        """
        Will return a dictionary of {coord: (filepath, page)} of length(N_Images) to later query
        Returns
        -------
        """
        if self.data_type == 'ometiff':
            for file in self.files:
                tf = tiff.TiffFile(file)
                meta = tf.micromanager_metadata['IndexMap']

                for page in range(len(meta['Channel'])):
                    coord = [0, 0, 0, 0]
                    coord[self.p_dim] = meta['Position'][page]
                    coord[self.t_dim] = meta['Frame'][page]
                    coord[self.c_dim] = meta['Channel'][page]
                    coord[self.z_dim] = meta['Slice'][page]

                    self.coord_map[tuple(coord)] = (file, page)
        else:
            pass

    def _gen_coordset(self):
        """
        generates a coordinate set in the dimensional order to which the data was acquired.
        This is important for keeping track of where we are in the tiff file during conversion

        Returns
        -------
        list(tuples) w/ length [N_images]

        """

        # if acquisition information is not present, make an arbitrary dimension order
        if not self.summary_metadata or 'AxisOrder' not in self.summary_metadata.keys():

            self.p_dim = 0
            self.t_dim = 1
            self.c_dim = 2
            self.z_dim = 3

            self.dim_order = ['position', 'time', 'channel', 'z']

            # Assume data was collected slice first
            dims = [self.reader.slices, self.reader.channels, self.reader.frames, self.reader.get_num_positions()]

        # get the order in which the data was collected to minimize i/o calls
        else:
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

            # Reverse the dimension order and gather dimension indices
            self.dim_order.reverse()
            self.p_dim = self.dim_order.index('position')
            self.t_dim = self.dim_order.index('time')
            self.c_dim = self.dim_order.index('channel')
            self.z_dim = self.dim_order.index('z')

        # create array of coordinate tuples with innermost dimension being the first dim acquired
        self.coords = [(dim3, dim2, dim1, dim0) for dim3 in range(dims[3]) for dim2 in range(dims[2])
                       for dim1 in range(dims[1]) for dim0 in range(dims[0])]

    def _get_position_coords(self):

        row_max = 0
        col_max = 0
        coords_list = []

        #TODO: read rows, cols directly from XY corods
        for idx, pos in enumerate(self.reader.stage_positions):
            coords_list.append(pos['XYStage'])
            row = pos['GridRowIndex']
            col = pos['GridColumnIndex']
            row_max = row if row > row_max else row_max
            col_max = col if col > col_max else col_max

        return coords_list, row_max, col_max

    def _generate_hcs_metadata(self):


        position_list, rows, cols = self._get_position_coords()

        position_grid = create_grid_from_coordinates(position_list, rows, cols)

        # Build metadata based off of position grid
        hcs_meta = {'plate': {
            'acquisitions': [{'id': 1,
                              'maximumfieldcount': 1,
                              'name': 'Dataset',
                              'starttime': 0}],
            'columns': [{'name': f'Col_{i}'} for i in range(cols)],

            'field_count': 1,
            'name': 'name',
            'rows': [{'name': f'Row_{i}'} for i in range(rows)],
            'version': '0.1',
            'wells': [{'path': f'Row_{i}/Col_{j}'} for i in range(rows) for j in range(cols)]},

            'well': [{'images': [{'path': f'Pos_{pos:03d}'}]} for pos in position_grid.flatten()]
        }

        self.hcs_meta = hcs_meta

    def _generate_plane_metadata(self, tiff_file, page):
        """
        generates the img plane metadata by saving the MicroManagerMetadata written in the tiff tags.

        This image-plane data houses information of the config when the image was acquired.

        Parameters
        ----------
        tiff_file:          (TiffFile Object) Opened TiffFile Object
        page:               (int) Page corresponding to the desired image plane

        Returns
        -------
        image_metadata:     (dict) Dictionary of the image-plane metadata

        """

        for tag in tiff_file.pages[page].tags.values():
            if tag.name == 'MicroManagerMetadata':
                return tag.value
            else:
                continue

    def _perform_image_check(self, tiff_image, coord):
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

        zarr_array = self.writer.sub_writer.current_pos_group['array']
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

        chan_names = self.reader.channel_names

        return chan_names

    def _get_position_names(self):
        """
        Append a list of pos_names in ascending order (order in which they were acquired)

        Returns
        -------

        """

        for p in range(self.p):
            if self.p > 1:
                name = self.summary_metadata['StagePositions'][p]['Label']
            else:
                name = ''
            self.pos_names.append(name)

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

    def get_image_array(self, p, t, c, z):
        """
        Grabs the image array through memory mapping.  We must first find the byte offset which is located in the
        tiff page tag.  We then use that to quickly grab the bytes corresponding to the desired image.

        Parameters
        ----------
        p:                  (int) position coordinate
        t:                  (int) time coordinate
        c:                  (int) channel coordinate
        z:                  (int) z coordinate

        Returns
        -------
        array:              (nd-array) image array of shape (Y, X)

        """

        # get virtual zarr store at given position
        zs = self.reader.get_zarr(p)

        # get image array
        array = zs[t, c, z]

        return array

    def get_channel_clims(self, pos):
        """
        generate contrast limits for each channel.  Grabs the middle image of the stack to compute contrast limits
        Default clim is to ignore 1% of pixels on either end

        Returns
        -------
        clims:      [list]: list of tuples corresponding to the (min, max) contrast limits

        """

        clims = []

        zs = self.reader.get_zarr(pos)

        for chan in range(self.c):

            img = zs[0, chan, self.focus_z]
            clims.append(get_autocontrast_limits(img))

        return clims

    def init_zarr_structure(self):
        """
        Initiates the zarr store.  Will create a zarr store with user-specified name or original name of data
        if not provided.  Store will contain a group called 'array' with contains an array of original
        data dtype of dimensions (T, C, Z, Y, X).  Appends OME-zarr metadata with clims,chan_names

        Current compressor is Blosc zstd w/ bitshuffle (~1.5x compression, faster compared to best 1.6x compressor)

        Returns
        -------

        """


        chan_names = self._get_channel_names()
        self._get_position_names()

        for pos in range(self.p):

            clims = self.get_channel_clims(pos)
            name = self.pos_names[pos] if self.replace_position_names else None
            self.writer.init_array(pos,
                                   data_shape=(self.t if self.t != 0 else 1,
                                               self.c if self.c != 0 else 1,
                                               self.z if self.z != 0 else 1,
                                               self.y,
                                               self.x),
                                   chunk_size=(1, 1, 1, self.y, self.x),
                                   chan_names=chan_names,
                                   clims=clims,
                                   dtype=self.dtype,
                                   position_name=name)

    def run_conversion(self):
        """
        Runs the data conversion through memory mapping and performs an image check to make sure conversion did not
        alter any data values.

        Returns
        -------

        """

        # Run setup
        print('Running Conversion...')
        print('Setting up zarr')
        self._gen_coordset()
        self._gather_index_maps()
        self.init_zarr_structure()
        last_file = None

        #Format bar for CLI display
        bar_format = 'Status: |{bar}|{n_fmt}/{total_fmt} (Time Remaining: {remaining}), {rate_fmt}{postfix}]'

        # Run through every coordinate and convert image + grab image metadata, statistics
        # loop is done in order in which the images were acquired
        print('Converting Images...')
        for coord in tqdm(self.coords, bar_format=bar_format):


            if self.data_type != 'upti':
                # Only load tiff file if it has changed from previous run
                current_file = self.coord_map[coord][0]
                if self.check_file_changed(last_file, current_file):
                    tf = tiff.TiffFile(current_file)
                    last_file = current_file

                # Get the metadata
                page = self.coord_map[coord][1]

                # re-order coordinates into zarr format
                coord_reorder = (coord[self.p_dim],
                                 coord[self.t_dim],
                                 coord[self.c_dim],
                                 coord[self.z_dim])

                meta = dict()
                plane_meta = self._generate_plane_metadata(tf, page)
                meta[f'{coord_reorder}'] = plane_meta

                # only write the plane metadata for the first time-point to avoid huge i/o overhead
                # rest will be placed in json file with the zarr store
                if coord[self.t_dim] == 0:
                    self.metadata['ImagePlaneMetadata'][f'{coord_reorder}'] = plane_meta
                    json.dump(meta, self.meta_file, indent=1)
                else:
                    json.dump(meta, self.meta_file, indent=1)
            # get the memory mapped image
            img_raw = self.get_image_array(coord[self.p_dim], coord[self.t_dim], coord[self.c_dim], coord[self.z_dim])

            # Write the data
            self.writer.write(img_raw, coord[self.p_dim], coord[self.t_dim], coord[self.c_dim], coord[self.z_dim])

            # Perform image check
            if not self._perform_image_check(img_raw, coord):
                raise ValueError('Converted zarr image does not match the raw data. Conversion Failed')

        # Put metadata into zarr store and cleanup
        self.writer.store.attrs.update(self.metadata)
        if self.meta_file:
            self.meta_file.close()