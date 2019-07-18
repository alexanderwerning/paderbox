import os
import platform
import numbers
import subprocess
import contextlib
from os import path

from distutils.version import LooseVersion

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
import seaborn as sns

from paderbox.visualization.new_cm import cmaps


# Still necessary?
mpl_ge_150 = LooseVersion(mpl.__version__) >= '1.5.0'


class DollarFormatter(ScalarFormatter):

    def __init__(self, *args, formatting, **kwargs):
        """
        Example for formatting: '{:.1f}'
        print with one digit of precision for floating point output

        """
        super().__init__(*args, **kwargs)
        self.formatting = formatting

    def __call__(self, x, pos=None):
        """Return the format for tick val *x* at position *pos*

        Args:
            x:
            pos:

        Returns:

        """
        if len(self.locs) == 0:
            return ''
        else:
            if not type(x) is str:
                if self.formatting is not None and x % 1:
                    s = self.formatting.format(x)
                else:
                    s = self.pprint_val(x)
                return '\$' + self.fix_minus(s) + '\$'
            else:
                return x


class LatexContextManager(object):
    """ Context manager used for plotting which exports and calls Inkscape.

    """
    def __init__(
            self,
            filename,
            export_type=None,  # eps recommended (alternative pdf), because pdf is in Inkscape 0.91 r not working
            build_folder=None,
            figure_size=(8.0, 6.0),
            formatter=None,
            format_x=True,
            format_y=True,
            palette=cmaps['upb'].colors[1:],
            extra_rc=None,
            ticks_formatting=None
    ):
        """

        Args:
            filename: Filename of the svg to be exported. I.e. test.svg
            figure_size: Tuple
            formatter: Default is a Dollar-formatter which changes the
                ticks labels from numbers to numbers sourrounded by dollar
                symbols.
            format_x: Disable formatter for x axis if False.
            format_y: Disable formatter for y axis if False.
            palette: Default color map
            extra_rc: Extra rc parameters for matplotlib
            export_type: Default None (only svg export), possibly
                eps (svg and eps_tex and eps export) and
                pdf (svg and pdf_tex and pdf export)

        Returns:

        """
        assert filename.endswith('.svg')
        self.filename = filename
        self.formatter = DollarFormatter(formatting=ticks_formatting) \
            if formatter is None else formatter
        self.figure_size = figure_size
        self.format_x = format_x
        self.format_y = format_y
        self.palette = palette
        self.build_folder = build_folder if build_folder is not None else path.dirname(filename)
        if extra_rc is None:
            self.extra_rc = dict()
        else:
            self.extra_rc = extra_rc
        self.export_type = export_type

    def __enter__(self):
        extra_rc = {
            'svg.fonttype': 'none',
            'text.usetex': False,
            'text.latex.unicode': False,
            'axes.unicode_minus': False
        }
        extra_rc.update(self.extra_rc)
        return figure_context(
            font_scale=2.5,
            extra_rc=extra_rc,
            figure_size=self.figure_size,
            palette=self.palette,
        )

    def __exit__(self, type, value, tb):
        figure = plt.gcf()
        for ax in figure.get_axes():
            if self.format_x:
                ax.xaxis.set_major_formatter(self.formatter)
            if self.format_y:
                ax.yaxis.set_major_formatter(self.formatter)
        if self.filename is not None:
            try:
                plt.savefig(self.filename)

                if platform.system() == 'Darwin':  # OS X
                    inkscape_path = ('/Applications/Inkscape.app/' +
                                     'Contents/Resources/bin/inkscape')
                else:
                    inkscape_path = 'inkscape'

                if self.export_type is not None:
                    # try:
                        # inkscape --help
                        # -z, --without-gui  Do not use X server (only process
                        #                    files from console)

                        # inkscape -z --export-area-page fig.svg --export-eps=fig.eps --export-latex
                        build_file = os.path.splitext(path.join(self.build_folder, path.basename(self.filename)))[0]\
                                     + '.' + self.export_type

                        cmd = [
                            inkscape_path, '-z', '--export-area-page',  # '--export-area-drawing',
                            os.path.realpath(self.filename),
                            '--export-{}={}'.format(
                                self.export_type,
                                os.path.realpath(build_file)),
                            '--export-latex'
                        ]
                        # print(*cmd)
                        subprocess.run(cmd)
                    # except:
                    #     print('Could not perform Inkscape export: {}.'.format(' '.join(cmd)))
            except FileNotFoundError as e:
                if not path.exists(path.dirname(self.filename)):
                    print('The folder {} does not exist.'.format(path.realpath(path.dirname(self.filename))))

                print('Could not save file {}. msg: {}'.format(self.filename, str(e)))
            # except:
            #    print('Could not save file {}.'.format(self.filename))


def figure_context(
    seaborn_axes_style='whitegrid',
    seaborn_plotting_context='notebook',
    font_scale=1.0,
    line_width=3,
    figure_size=(8.0, 6.0),
    palette='muted',
    extra_rc=None,
    color_skip=0,
):
    """ Helper to create a plotting style with auto completion.

    :param seaborn_axes_style:
        One of the seaborn axes style presets. You can choose from
        `darkgrid``, ``whitegrid``, ``dark``, ``white``, and ``ticks``
        and find further details in the
        `seaborn tutorial <http://stanford.edu/~mwaskom/software/seaborn-dev/tutorial/aesthetics.html#styling-figures-with-axes-style-and-set-style>`_.
    :param seaborn_plotting_context:
        One of the seaborn plotting contexts. You can choose from
        ``notebook``, ``paper``, ``talk``, and ``poster``.
        Further details are here in the
        `seaborn tutorial <http://stanford.edu/~mwaskom/software/seaborn-dev/generated/seaborn.plotting_context.html#seaborn-plotting-context>`_.
    :param font_scale:
        The font scale scales all fonts at the same time relative
        to the seaborn plotting context default.
        A factor of ``2.0`` is already quite large.
    :param line_width:
        Line width in line plots.
    :param figure_size:
        Figure size in inches: width, height as a tuple
    :param extra_rc:
        Any other matplotlib rc parameter.
        You can get a list of all rc parameters by calling
        ``plt.rcParamsDefault``.
        If you frequently change a specific parameter, you are encouraged to
        add this parameter to the list of named parameters just as has been
        done with ``figure_size``.
    :return: A context manager to be used around your plots.
    """
    axes_style = sns.axes_style(seaborn_axes_style)

    rc_parameters = {
        'lines.linewidth': line_width,
        'figure.figsize': figure_size,
    }

    # Improve grid lines for log plots. Allowed values: minor, major, both.
    rc_parameters['axes.grid.which'] = 'both'

    colors = sns.palettes.color_palette(sns.color_palette(palette))

    if mpl_ge_150:
        from cycler import cycler
        mul = len(colors)
        colors = 4*colors
        cyl = cycler('color', colors) + cycler(
            'linestyle', [*mul*['-'], *mul*['--'], *mul*[':'], *mul*['-.']])
        rc_parameters.update({
            'axes.prop_cycle': cyl[color_skip:]
        })
    else:
        rc_parameters.update({
            'axes.prop_cycle': list(colors)[color_skip:]
        })

    rc_parameters.update({
        'patch.facecolor': colors[0]
    })

    plotting_context = sns.plotting_context(
        seaborn_plotting_context,
        font_scale=font_scale,
    )

    if extra_rc is None:
        extra_rc = dict()
    rc_parameters.update(extra_rc)

    final = dict(axes_style, **plotting_context)
    final.update(rc_parameters)

    return plt.rc_context(final)


class _AxesHandler:
    # See axes_context for use case
    # Should this class be public?
    def _new_subplot(self):
        figure, axis = plt.subplots(1, self._columns, **self.subplot_kwargs)
        return figure, axis.flatten()

    def __init__(self, columns, subplot_kwargs=None):
        self._columns = columns
        self.subplots = []
        self.counter = -1
        self.subplot_kwargs = subplot_kwargs

        if self.subplot_kwargs is None:
            self.subplot_kwargs = dict()

        if 'squeeze' not in self.subplot_kwargs:
            self.subplot_kwargs = self.subplot_kwargs.copy()
            self.subplot_kwargs['squeeze'] = False
        elif self.subplot_kwargs['squeeze'] is not False:
            raise AssertionError(
                f'The squeeze argument for subplots in'
                f'{self.__class__.__name__} has to be False.\n'
                f'Got: squeeze = {self.subplot_kwargs["squeeze"]}'
            )

    def get_axes(self, *, row, col):
        while row >= len(self.subplots):
            self.subplots.append(self._new_subplot())
        axes = self.subplots[row][1]
        self.counter = max(self.counter, row * self._columns + col)
        return axes[col]

    @property
    def new(self):
        return self[self.counter + 1]

    @property
    def last(self):
        return self[self.counter]

    def __getitem__(self, item):
        if isinstance(item, numbers.Integral):
            if item < 0:
                item % self.counter
            row = item // self._columns
            col = item % self._columns
            return self.get_axes(row=row, col=col)
        elif isinstance(item, (tuple, list)):
            row, col = item
            return self.get_axes(row=row, col=col)
        else:
            raise TypeError(item)


@contextlib.contextmanager
def axes_context(
        columns=1,
        font_scale=1.0,
        line_width=3,
        figure_size=(8.0, 6.0),
        subplot_kwargs=None
):
    """

    Combine figure_context and _AxesHandler (similar use case as faced_grid).
    Note:
        figure_size will be a the figure size of one plot and not the size of
        all subplots.

     >>> with axes_context(2) as axes:
     ...     axes.new.plot([1,2,3])
     ...     axes.new.plot([1,2,3])
     ...     axes.last.plot([1,2,4])
     ...     axes.axes[1].plot([1,2,4])
     ...     axes.axes[1, 1].plot([1,2,4])

     - integrate context manager
     - integrate all plot functions

    """
    figure_size = list(figure_size)
    figure_size[0] *= columns
    with figure_context(
            font_scale=font_scale,
            line_width=line_width,
            figure_size=figure_size,
    ):
        yield _AxesHandler(columns, subplot_kwargs=subplot_kwargs)
