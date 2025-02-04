"""
This module deals with all sorts of audio input and output.
"""
import inspect
import os
import tempfile
import wave
import types
from io import BytesIO
from pathlib import Path
import functools

import numpy as np
import soundfile

import paderbox.utils.process_caller as pc
from paderbox.io.path_utils import normalize_path

UTILS_DIR = os.path.join(os.path.dirname(__file__), 'utils')


def load_audio(
        path,
        *,
        frames=-1,
        start=0,
        stop=None,
        channel=None,
        dtype=np.float64,
        fill_value=None,
        expected_sample_rate=None,
        unit='samples',
        return_sample_rate=False,
):
    """
    WIP will deprecate audioread in the future

    Difference to soundfile.read:
     - Default: Return only signal
     - With the argument "unit" the unit of frames, start and stop can be
       changed (stop currently unsupported).
     - With given expected_sample_rate an assert is included (recommended)

    soundfile.read doc text and some examples:

    Provide audio data from a sound file as NumPy array.

    By default, the whole file is read from the beginning, but the
    position to start reading can be specified with `start` and the
    number of frames to read can be specified with `frames`.
    Alternatively, a range can be specified with `start` and `stop`.

    If there is less data left in the file than requested, the rest of
    the frames are filled with `fill_value`.
    If no `fill_value` is specified, a smaller array is returned.

    Parameters
    ----------
    path : str or int or file-like object
        The file to read from.  See :class:`SoundFile` for details.

        The file name can be postfixed with an index, separated by a double
        colon `::`, for example `.../file.wav::[8000:16000,0]`.
        The first dimenion of the indexing expression determines the sample
        index and the second one the channel index. The sample index
        must always be a slice. The channel index is optional and can be
        a slice or an integer.

        Specifing this in the path is equivalent to setting the
        `start`, `stop` and `channel` parameters. The `start`, `stop`,
        `channel` and `frames` parameters have to be empty (not set) when
        using the slice notation.
    frames : int, optional
        The number of frames to read. If `frames` is negative, the whole
        rest of the file is read.  Not allowed if `stop` is given.
    start : int, optional
        Where to start reading.  A negative value counts from the end.
    stop : int, optional
        The index after the last frame to be read.  A negative value
        counts from the end.  Not allowed if `frames` is given.
    channel : int or slice or list of int or tuple of int
        Channel(s) to select from a multichannel audio file. Can be anything
        that can index a numpy array along a single dimension.
    dtype : {'float64', 'float32', 'int32', 'int16'}, optional
        Data type of the returned array, by default ``'float64'``.
        Floating point audio data is typically in the range from
        ``-1.0`` to ``1.0``.  Integer data is in the range from
        ``-2**15`` to ``2**15-1`` for ``'int16'`` and from ``-2**31`` to
        ``2**31-1`` for ``'int32'``.

        .. note:: Reading int values from a float file will *not*
            scale the data to [-1.0, 1.0). If the file contains
            ``np.array([42.6], dtype='float32')``, you will read
            ``np.array([43], dtype='int32')`` for ``dtype='int32'``.
    unit: 'samples' or 'seconds'
        The unit of `start`, `stop` and `frames` values
    expected_sample_rate: int, optional
        The expected sample rate of the loaded audio file. This function raises
        a ValueError when the sample rate of the file differs from
        `expected_sample_rate`
    fill_value : float, optional
        If more frames are requested than available in the file, the
        rest of the output is being filled with `fill_value`.  If
        `fill_value` is not specified, a smaller array is returned.
    return_sample_rate: bool
        Whether to return the sample rate as a second element

    Returns
    -------
    audiodata : numpy.ndarray
        A two-dimensional (frames x channels) NumPy array is returned.
        If the sound file has only one channel, a one-dimensional array
        is returned.
    audiodata, sample_rate : (numpy.ndarray, int)
        Additionally the sample reate is returned when `return_sample_rate`
        is set to `True`.

    Examples
    --------
    >>> import sys, pytest
    >>> if sys.platform.startswith("win"):
    ...     pytest.skip("Removed from windows tests")
    >>> from paderbox.io import load_audio
    >>> from paderbox.testing.testfile_fetcher import get_file_path
    >>> path = get_file_path('speech.wav')
    >>> data = load_audio(path)
    >>> data.shape
    (49600,)
    >>> data = load_audio(Path(str(path) + '::[8000:16000]'))
    >>> data.shape
    (8000,)

    Multichannel file:
    >>> path = get_file_path('observation.wav')
    >>> data = load_audio(path)
    >>> data.shape
    (6, 38520)
    >>> data = load_audio(str(path) + '::[:,0]')
    >>> data.shape
    (38520,)
    >>> data = load_audio(str(path) + '::[:,:2]')
    >>> data.shape
    (2, 38520)
    >>> data = load_audio(str(path) + '::[:,2:4]')
    >>> data.shape
    (2, 38520)
    >>> data = load_audio(path, channel=[1, 3, 5])
    >>> data.shape
    (3, 38520)

    Say you load audio examples from a very long audio, you can provide a
    start position and a duration in samples or seconds.

    >>> path = get_file_path('speech.wav')
    >>> signal = load_audio(path, start=0, frames=16_000)
    >>> signal.shape
    (16000,)
    >>> signal = load_audio(path, start=0, frames=1, unit='seconds')
    >>> signal.shape
    (16000,)

    If the audio file is to short, only return the defined part:

    >>> signal = load_audio(path, start=0, frames=160_000)
    >>> signal.shape
    (49600,)

    >>> path = get_file_path('123_1pcbe_shn.sph')
    >>> load_audio(path)  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    RuntimeError: Wrong suffix .sph in ...123_1pcbe_shn.sph.
    File format:
    ...123_1pcbe_shn.sph: NIST SPHERE file
    """

    # soundfile does not support pathlib.Path.
    # ToDo: Is this sill True?
    path = normalize_path(path, as_str=True)

    # Set start and stop when encoded in the filename
    if isinstance(path, str) and '::' in path:
        assert unit == 'samples', unit
        assert frames == -1, frames
        path, start, stop, channel = _parse_audio_slice(
            path, start, stop, channel
        )

    if unit == 'samples':
        pass
    elif unit == 'seconds':
        if stop is not None:
            if stop < 0:
                raise NotImplementedError(unit, stop)
        with soundfile.SoundFile(path) as f:
            # total_samples = len(f)
            samplerate = f.samplerate
        start = int(np.round(start * samplerate))
        if frames > 0:
            frames = int(np.round(frames * samplerate))
        if stop is not None and stop > 0:
            stop = int(np.round(stop * samplerate))
    else:
        raise ValueError(unit)

    try:
        if isinstance(path, (str, Path)) and (Path(path).suffix == '.m4a'):
            import audioread
            assert (start == 0 and stop is None), \
                'audioread does not support partial loading of audio files'
            with audioread.audio_open(
                    path
            ) as f:
                sample_rate = f.samplerate
                data = []
                scale = 1. / float(1 << (15))
                for buf in f:
                    data.append(
                        np.frombuffer(buf, "<i2").astype(np.float64) * scale)
                signal = np.concatenate(data)
        else:
            with soundfile.SoundFile(
                    path,
                    'r',
            ) as f:
                if dtype is None:
                    from paderbox.utils.mapping import Dispatcher
                    mapping = Dispatcher({
                        'PCM_16': np.int16,
                        'FLOAT': np.float32,
                        'DOUBLE': np.float64,
                    })
                    dtype = mapping[f.subtype]

                frames = f._prepare_read(start=start, stop=stop, frames=frames)
                data = f.read(
                    frames=frames, dtype=dtype, fill_value=fill_value,
                    always_2d=channel is not None
                )
            signal, sample_rate = data, f.samplerate
    except RuntimeError as e:
        if isinstance(path, (Path, str)):
            import magic
            # recreate the stdout of the 'file' tool
            msg = Path(path).as_posix() + ": " + magic.from_file(str(path))
            if Path(path).suffix == '.wav':
                # Improve exception msg for NIST SPHERE files.
                raise RuntimeError(
                    f'Could not read {path}.\n'
                    f'File format:\n{msg}'
                ) from e
            else:
                path = Path(path)
                raise RuntimeError(
                    f'Wrong suffix {path.suffix} in {path}.\n'
                    f'File format:\n{msg}'
                ) from e
        raise

    if expected_sample_rate is not None:
        if expected_sample_rate != sample_rate:
            raise ValueError(
                f'Requested sampling rate is {expected_sample_rate} but the '
                f'audiofile has {sample_rate}'
            )

    # When signal is multichannel, then soundfile returns (samples, channels)
    # At NT it is more common to have the shape (channels, samples)
    # => transpose
    signal = signal.T

    # Slice along channel dimension if channel_slice is given
    if channel is not None:
        assert signal.ndim == 2, (signal.shape, channel)
        signal = signal[channel, ]
        if signal.size == 0:
            raise ValueError('Returned signal would be empty')

    if return_sample_rate:
        return signal, sample_rate
    else:
        return signal


# https://jex.im/regulex/#!flags=&re=%5C%5B(%5Cd%2B)%3F%3A(%5Cd%2B)%3F(%3F%3A%2C(%3F%3A(%5Cd%2B)%3F%3A(%5Cd%2B)%3F%7C(%5Cd%2B)%3F))%3F%5C%5D
_PATTERN = r'\[(\d+)?:(\d+)?(?:,(?:(\d+)?:(\d+)?|(\d+)?))?\]'


def _parse_audio_slice(
        path,
        start=0,
        stop=None,
        channel=None,
):
    """
    >>> import re
    >>> re.fullmatch(_PATTERN, '[:]').groups()
    (None, None, None, None, None)
    >>> re.fullmatch(_PATTERN, '[:3]').groups()
    (None, '3', None, None, None)
    >>> re.fullmatch(_PATTERN, '[3:]').groups()
    ('3', None, None, None, None)
    >>> re.fullmatch(_PATTERN, '[3:4]').groups()
    ('3', '4', None, None, None)
    >>> re.fullmatch(_PATTERN, '[:,1]').groups()
    (None, None, None, None, '1')
    >>> re.fullmatch(_PATTERN, '[:,1:]').groups()
    (None, None, '1', None, None)
    >>> re.fullmatch(_PATTERN, '[:,:]').groups()
    (None, None, None, None, None)
    >>> re.fullmatch(_PATTERN, '[:,1:2]').groups()
    (None, None, '1', '2', None)
    >>> re.fullmatch(_PATTERN, '[:,:2]').groups()
    (None, None, None, '2', None)

    >>> _parse_audio_slice('file.wav::[:16000,0]')
    ('file.wav', 0, 16000, 0)
    >>> _parse_audio_slice('file.wav::[:16000,:2]')
    ('file.wav', 0, 16000, slice(None, 2, None))
    """
    import re

    assert start == 0, start
    assert stop is None, stop
    assert channel is None, channel
    _path, audio_slice = path.rsplit('::', maxsplit=1)
    assert ' ' not in audio_slice, audio_slice

    try:
        start, stop, channel_start, channel_stop, channel = map(
            lambda x: x if x is None else int(x),
            re.fullmatch(_PATTERN, audio_slice).groups()
        )
    except Exception as e:
        raise ValueError(path) from e

    if channel is None and not (channel_start is None and channel_stop is None):
        channel = slice(channel_start, channel_stop)

    if start is None:
        start = 0

    return _path, start, stop, channel


def recursive_load_audio(
        path,
        *,
        frames=-1,
        start=0,
        stop=None,
        dtype=np.float64,
        fill_value=None,
        expected_sample_rate=None,
        unit='samples',
        return_sample_rate=False,
):
    """
    Recursively loads all leafs (i.e. tuple/list entry or dict value) in the
    object `path`. `path` can be a nested structure, but can also be a str or
    pathlib.Path. When the entry type was a tuple or list, try to convert that
    object to a np.array with a dytpe different from np.object.

    For an explanation of the arguments, see `load_audio`.

    >>> from paderbox.testing.testfile_fetcher import get_file_path
    >>> from paderbox.notebook import pprint
    >>> path1 = get_file_path('speech.wav')
    >>> path2 = get_file_path('sample.wav')
    >>> pprint(recursive_load_audio(path1))
    array(shape=(49600,), dtype=float64)
    >>> pprint(recursive_load_audio([path1, path1]))
    array(shape=(2, 49600), dtype=float64)
    >>> pprint(recursive_load_audio([path1, path2]))
    [array(shape=(49600,), dtype=float64), array(shape=(38520,), dtype=float64)]
    >>> pprint(recursive_load_audio({'a': path1, 'b': path1}))
    {'a': array(shape=(49600,), dtype=float64),
     'b': array(shape=(49600,), dtype=float64)}
    >>> pprint(recursive_load_audio([path1, (path2, path2)]))
    [array(shape=(49600,), dtype=float64), array(shape=(2, 38520), dtype=float64)]

    """
    kwargs = locals().copy()
    path = kwargs.pop('path')

    if isinstance(path, (tuple, list, types.GeneratorType)):
        data = [recursive_load_audio(a, **kwargs) for a in path]

        try:
            np_data = np.array(data)
        except ValueError:
            return data
        else:
            # old numpy
            if np_data.dtype != object:
                return np_data
            else:
                return data
    elif isinstance(path, dict):
        return {k: recursive_load_audio(v, **kwargs) for k, v in path.items()}
    else:
        return load_audio(path, **kwargs)


def audioread(path, offset=0.0, duration=None, expected_sample_rate=None):
    """
    Reads a wav file, converts it to 32 bit float values and reshapes according
    to the number of channels.

    This function uses the `wavefile` module which in turn uses `libsndfile` to
    read an audio file. This is much faster than the previous version based on
    `librosa`, especially if one reads a short segment of a long audio file.

    .. note:: Contrary to the previous version, this one does not implicitly
        resample the audio if the `sample_rate` parameter differs from the
        actual sampling rate of the file. Instead, it raises an error.


    :param path: Absolute or relative file path to audio file.
    :type: String.
    :param offset: Begin of loaded audio.
    :type: Scalar in seconds.
    :param duration: Duration of loaded audio.
    :type: Scalar in seconds.
    :param sample_rate: (deprecated) Former audioread did implicit resampling
        when a different sample rate was given. This raises an error if the
        `sample_rate` does not match the files sampling rate. `None` accepts
        any rate.
    :type: scalar in number of samples per second
    :return:

    .. admonition:: Example:
        Only path provided:

        >>> import sys, pytest
        >>> if sys.platform.startswith("win"):
        ...     pytest.skip("`pb.io.audioread.audioread` is deprecated and "
        ...                "does not work on windows, because wavefile needs "
        ...                "`libsndfile-1.dll`."
        ...                "Use `pb.io.load_audio` on windows.")
        >>> from paderbox.testing.testfile_fetcher import get_file_path
        >>> path = get_file_path('speech.wav')
        >>> # path = '/net/db/timit/pcm/train/dr1/fcjf0/sa1.wav'
        >>> signal, sample_rate = audioread(path)
        >>> signal.shape
        (49600,)

        Say you load audio examples from a very long audio, you can provide a
        start position and a duration in seconds.

        >>> path = get_file_path('speech.wav')
        >>> # path = '/net/db/timit/pcm/train/dr1/fcjf0/sa1.wav'
        >>> signal, sample_rate = audioread(path, offset=0, duration=1)
        >>> signal.shape
        (16000,)
        >>> signal, sample_rate = audioread(path, offset=0, duration=10)
        >>> signal.shape
        (160000,)

        >>> path = get_file_path('123_1pcbe_shn.sph')
        >>> audioread(path)  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        OSError: .../123_1pcbe_shn.sph: NIST SPHERE file
        <BLANKLINE>
    """
    import wavefile
    if isinstance(path, Path):
        path = str(path)
    path = os.path.expanduser(path)

    try:
        with wavefile.WaveReader(path) as wav_reader:
            channels = wav_reader.channels
            sample_rate = wav_reader.samplerate
            if expected_sample_rate is not None and expected_sample_rate != sample_rate:
                raise ValueError(
                    'Requested sampling rate is {} but the audiofile has {}'.format(
                        expected_sample_rate, sample_rate
                    )
                )

            if duration is None:
                samples = wav_reader.frames - int(np.round(offset * sample_rate))
                frames_before = int(np.round(offset * sample_rate))
            else:
                samples = int(np.round(duration * sample_rate))
                frames_before = int(np.round(offset * sample_rate))

            data = np.zeros((channels, samples), dtype=np.float32, order='F')
            wav_reader.seek(frames_before)
            wav_reader.read(data)
            return np.squeeze(data), sample_rate
    except OSError as e:
        from paderbox.utils.process_caller import run_process
        cp = run_process(f'file {path}')
        stdout = cp.stdout
        raise OSError(f'{stdout}') from e


def audio_length(path, unit='samples'):
    """

    Args:
        path:
        unit:

    Returns:

    >>> from paderbox.testing.testfile_fetcher import get_file_path
    >>> path = get_file_path('speech_source_0.wav')
    >>> audio_length(path)
    38520
    >>> path = get_file_path('speech_image_0.wav')
    >>> audio_length(path)  # correct for multichannel
    38520
    >>> with soundfile.SoundFile(str(path)) as f:
    ...     print(f.read().shape)
    (38520, 6)
    """

    # params = soundfile.info(str(path))
    # return int(params.samplerate * params.duration)

    if unit == 'samples':
        with soundfile.SoundFile(str(path)) as f:
            return len(f)
    elif unit == 'seconds':
        with soundfile.SoundFile(str(path)) as f:
            return len(f) / f.samplerate
    else:
        return ValueError(unit)


def audio_channels(path):
    """
    >>> import sys, pytest
    >>> if sys.platform.startswith("win"):
    ...     pytest.skip("`pb.io.audioread.audioread` is deprecated and "
    ...                "does not work on windows, because wavefile needs "
    ...                "`libsndfile-1.dll`.")
    >>> from paderbox.testing.testfile_fetcher import get_file_path
    >>> path = get_file_path('speech_source_0.wav')
    >>> audio_channels(path)
    1
    >>> path = get_file_path('speech_image_0.wav')
    >>> audio_channels(path)  # correct for multichannel
    6
    """
    with soundfile.SoundFile(str(path)) as f:
        return f.channels


def audio_shape(path):
    """
    >>> import sys, pytest
    >>> if sys.platform.startswith("win"):
    ...     pytest.skip("`pb.io.audioread.audioread` is deprecated and "
    ...                "does not work on windows, because wavefile needs "
    ...                "`libsndfile-1.dll`.")
    >>> from paderbox.testing.testfile_fetcher import get_file_path
    >>> path = get_file_path('speech_source_0.wav')
    >>> audio_shape(path)
    38520
    >>> path = get_file_path('speech_image_0.wav')
    >>> audio_shape(path)  # correct for multichannel
    (6, 38520)
    >>> audioread(path)[0].shape
    (6, 38520)
    """
    with soundfile.SoundFile(str(path)) as f:
        channels = f.channels
        if channels == 1:
            return len(f)
        else:
            return channels, len(f)


def is_nist_sphere_file(path):
    """Check if given path is a nist/sphere file"""
    if not os.path.exists(path):
        return False
    cmd = f'file {path}'
    return 'NIST SPHERE file' in pc.run_process(cmd).stdout


def read_nist_wsj(path, audioread_function=audioread, **kwargs):
    """
    Converts a nist/sphere file of wsj and reads it with audioread.

    :param path: file path to audio file.
    :param audioread_function: Function to use to read the resulting audio file
    :return:
    """
    tmp_file = tempfile.NamedTemporaryFile(delete=False)
    cmd = "{}/sph2pipe -f wav {path} {dest_file}".format(
        UTILS_DIR, path=path, dest_file=tmp_file.name
    )
    pc.run_processes(cmd, ignore_return_code=False)
    signal = audioread_function(tmp_file.name, **kwargs)
    os.remove(tmp_file.name)
    return signal


def read_raw(path, dtype=np.dtype('<i2')):
    """
    Reads raw data (tidigits data)

    :param path: file path to audio file
    :param dtype: datatype, default: int16, little-endian
    :return: numpy array with audio samples
    """

    if isinstance(path, Path):
        path = str(path)

    with open(path, 'rb') as f:
        return np.fromfile(f, dtype=dtype)


def getparams(path):
    """
    Returns parameters of wav file.

    :param path: Absolute or relative file path to audio file.
    :type: String.
    :return: Named tuple with attributes (nchannels, sampwidth, framerate,
    nframes, comptype, compname)
    """
    with wave.open(str(path), 'r') as wave_file:
        return wave_file.getparams()


def read_from_byte_string(byte_string, dtype=np.dtype('<i2')):
    """ Parses a bytes string, i.e. a raw read of a wav file

    :param byte_string: input bytes string
    :param dtype: dtype used to decode the audio data
    :return: np.ndarray with audio data with channels x samples
    """
    wav_file = wave.openfp(BytesIO(byte_string))
    channels = wav_file.getnchannels()
    interleaved_audio_data = np.frombuffer(
        wav_file.readframes(wav_file.getnframes()), dtype=dtype)
    audio_data = np.array(
        [interleaved_audio_data[ch::channels] for ch in range(channels)])
    audio_data = audio_data.astype(np.float32) / np.max(audio_data)
    return audio_data
