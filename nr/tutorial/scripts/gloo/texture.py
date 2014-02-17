# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2014, Nicolas P. Rougier. All rights reserved.
# Distributed under the terms of the new BSD License.
# -----------------------------------------------------------------------------
import numpy as np
import OpenGL.GL as gl
from operator import mul

from debug import log
from globject import GLObject



# ----------------------------------------------------------- Texture class ---
class Texture(GLObject):
    """
    Test
    """

    _formats = {
        1 : gl.GL_LUMINANCE, #//ALPHA,
        2 : gl.GL_LUMINANCE_ALPHA,
        3 : gl.GL_RGB,
        4 : gl.GL_RGBA
    }

    _types = {
        np.dtype(np.int8)    : gl.GL_BYTE,
        np.dtype(np.uint8)   : gl.GL_UNSIGNED_BYTE,
        np.dtype(np.int16)   : gl.GL_SHORT,
        np.dtype(np.uint16)  : gl.GL_UNSIGNED_SHORT,
        np.dtype(np.int32)   : gl.GL_INT,
        np.dtype(np.uint32)  : gl.GL_UNSIGNED_INT,
        # np.dtype(np.float16) : gl.GL_HALF_FLOAT,
        np.dtype(np.float32) : gl.GL_FLOAT,
        # np.dtype(np.float64) : gl.GL_DOUBLE
    }


    def __init__(self, data=None, shape=(), dtype=None, base=None, target=None,
                       offset=None, store=True, copy=False, resizeable=True):
        """
        Initialize the texture

        Parameters
        ----------

        target : GLEnum
            gl.GL_TEXTURE1D, gl.GL_TEXTURE2D

        data : np.ndarray
            Texture data (optional)

        dtype : np.dtype
            Texture data type (optional)

        shape : tuple of integers
            Texture shape

        base : Texture
           Base texture of this texture

        offset : tuple of integers
           Offset of this texture relative to base texture

        store : boolean
           Indicate whether to use an intermediate CPU storage

        copy : boolean
           Indicate whether to use given data as CPU storage

        resizeable : boolean
            Indicates whether texture can be resized
        """

        GLObject.__init__(self)
        self._data = None
        self._base = base
        self._store = store
        self._copy = copy
        self._target = target
        self._offset = offset
        self._pending_data = []
        self._resizeable = resizeable
        self._need_resize = False
        self._need_update = False
        self._valid = True
        self._views = []

        self._interpolation = gl.GL_NEAREST, gl.GL_NEAREST
        self._wrapping = gl.GL_CLAMP_TO_EDGE
        self._need_parameterization = True

        # Do we have data to build texture upon ?
        if data is not None:
            self._need_resize = True
            if dtype is not None:
                data = np.array(data,dtype=dtype,copy=False)
            else:
                data = np.array(data,copy=False)
            self._dtype = data.dtype
            self._shape = data.shape
            if self._store:
                if base is None and not data.flags["C_CONTIGUOUS"]:
                    self._copy = True
                self._data = np.array(data,copy=self._copy)
                self.set_data(self.data,copy=False)
            else:
                self.set_data(data,copy=True)
        elif dtype is not None:
            if shape:
                self._need_resize = True
            self._shape = shape
            self._dtype = dtype
            if self._store:
                self._data = np.empty(self._shape, dtype=self._dtype)
        else:
            raise ValueError("Either data or dtype must be given")

        if offset is None:
            self._offset = (0,) * len(self._shape)
        else:
            self._offset = offset

        self._gtype = Texture._types.get(self.dtype, None)
        if self._gtype is None:
            raise ValueError("Type not allowed for texture")



    @property
    def shape(self):
        """ Texture shape """

        return self._shape


    @property
    def offset(self):
        """ Texture offset """

        return self._offset


    @property
    def dtype(self):
        """ Texture data type """

        return self._dtype


    @property
    def base(self):
        """ Texture base if this texture is a view on another texture """

        return self._base


    @property
    def data(self):
        """ Texture CPU storage """

        return self._data

    @property
    def wrapping(self):
        """ Texture wrapping mode """

        if base is not None:
            return self.base.wrapping
        return self._wrapping


    @wrapping.setter
    def wrapping(self, value):
        """ Texture wrapping mode """

        if base is not None:
            raise ValueError("Cannot set wrapping on texture view")

        assert value in (gl.GL_REPEAT, gl.GL_CLAMP_TO_EDGE, gl.GL_MIRRORED_REPEAT)
        self._wrapping = value
        self._need_parameterization = True


    @property
    def interpolation(self):
        """ Texture interpolation for minification and magnification. """

        if base is not None:
            return self.base.interpolation

        return self._interpolation


    @interpolation.setter
    def interpolation(self, value):
        """ Texture interpolation for minication and magnification. """

        if self.base is not None:
            raise ValueError("Cannot set interpolation on texture view")

        assert value in (gl.GL_NEAREST, gl.GL_LINEAR)
        self._interpolation = value
        self._need_parameterization = True


    def resize(self, shape):
        """ Resize the texture (deferred operation)

        Parameters
        ----------

        shape : tuple of integers
            New texture shape

        Note
        ----

        This clears any pending operations.
        """

        if not self._resizeable:
            raise RuntimeError("Texture is not resizeable")

        if self._base is not None:
            raise RuntimeError("Texture view is not resizeable")

        if len(shape) != len(self.shape):
            raise ValueError("New shape has wrong number of dimensions")

        if shape == self.shape:
            return

        # Invalidate any view on this texture
        for view in self._views:
            view._valid = False
        self._views = []

        self._pending_data = []
        self._need_update = False
        self._shape = shape
        if self._data is not None and self._store:
            self._data = np.resize(self._data, self._data.shape)
        else:
            self._data = None



    def set_data(self, data, offset=None, copy=False):
        """
        Set data (deferred operation)

        Parameters
        ----------

        data : np.array
            Data to be uploaded

        offset: int or tuple of ints
            Offset in texture where to start copying data

        copy: boolean
            Since the operation is deferred, data may change before
            data is actually uploaded to GPU memory.
            Asking explicitly for a copy will prevent this behavior.

        Note
        ----

        This operation implicitely resizes the texture to the shape of the data
        if given offset is None.
        """

        if self.base is not None and not self._valid:
            raise ValueError("This texture view has been invalited")

        if self.base is not None:
            self.base.set_data(data, offset=self.offset, copy=copy)
            return

        # Check data has the right shape
        # if len(data.shape) != len(self.shape):
        #  raise ValueError("Data has wrong shape")

        # Check if resize needed
        if offset is None:
            if data.shape != self.shape:
                self.resize(data.shape)

        if offset is None or  offset == (0,)*len(self.shape):
            if data.shape == self.shape:
                self._pending_data = []

            # Convert offset to something usable
            offset = (0,)*len(self.shape)

        # Check if data fits
        for i in range(len(data.shape)):
            if offset[i]+data.shape[i] > self.shape[i]:
                raise ValueError("Data is too large")

        # Make sure data is contiguous
        if not data.flags["C_CONTIGUOUS"]:
            data = np.array(data,copy=True)
        else:
            data = np.array(data,copy=copy)

        self._pending_data.append( (data, offset) )
        self._need_update = True



    def __getitem__(self, key):
        """ x.__getitem__(y) <==> x[y] """

        if self.base is not None:
            raise ValueError("Can only access data from a base texture")

        # Make sure key is a tuple
        if type(key) in [int, slice] or key == Ellipsis:
            key = (key,)

        # Default is to access the whole texture
        shape = self.shape
        slices = [slice(0,shape[i]) for i in range(len(shape))]

        # Check last key/Ellipsis to decide on the order
        keys = key[::+1]
        dims = range(0,len(key))
        if key[0] == Ellipsis:
            keys = key[::-1]
            dims = range(len(self.shape)-1,len(self.shape)-1-len(keys),-1)


        # Find exact range for each key
        for k,dim in zip(keys,dims):
            size = self.shape[dim]
            if isinstance(k, int):
                if k < 0:
                    k += size
                if k < 0 or k > size:
                    raise IndexError("Texture assignment index out of range")
                start, stop = k, k+1
                slices[dim] = slice(start, stop, 1)
            elif isinstance(k, slice):
                start, stop, step = k.indices(size)
                if step != 1:
                    raise ValueError("Cannot access non-contiguous data")
                if stop < start:
                    start, stop = stop, start
                slices[dim] = slice(start, stop, step)
            elif k == Ellipsis:
                pass
            else:
                raise TypeError("Texture indices must be integers")

        offset = tuple([s.start for s in slices])
        shape = tuple([s.stop-s.start for s in slices])
        data = None
        if self.data is not None:
            data = self.data[slices]

        T = self.__class__(dtype=self.dtype, shape=shape,
                           base=self, offset=offset, resizeable=False)
        T._data = data
        self._views.append(T)
        return T



    def __setitem__(self, key, data):
        """ x.__getitem__(y) <==> x[y] """

        if self.base is not None and not self._valid:
            raise ValueError("This texture view has been invalited")

        # Make sure key is a tuple
        if type(key) in [int, slice] or key == Ellipsis:
            key = (key,)

        # Default is to access the whole texture
        shape = self.shape
        slices = [slice(0,shape[i]) for i in range(len(shape))]

        # Check last key/Ellipsis to decide on the order
        keys = key[::+1]
        dims = range(0,len(key))
        if key[0] == Ellipsis:
            keys = key[::-1]
            dims = range(len(self.shape)-1,len(self.shape)-1-len(keys),-1)

        # Find exact range for each key
        for k,dim in zip(keys,dims):
            size = self.shape[dim]
            if isinstance(k, int):
                if k < 0:
                    k += size
                if k < 0 or k > size:
                    raise IndexError("Texture assignment index out of range")
                start, stop = k, k+1
                slices[dim] = slice(start, stop, 1)
            elif isinstance(k, slice):
                start, stop, step = k.indices(size)
                if step != 1:
                    raise ValueError("Cannot access non-contiguous data")
                if stop < start:
                    start, stop = stop, start
                slices[dim] = slice(start, stop, step)
            elif k == Ellipsis:
                pass
            else:
                raise TypeError("Texture indices must be integers")

        offset = tuple([s.start for s in slices])
        shape = tuple([s.stop-s.start for s in slices])
        size = reduce(mul,shape)

        # We have CPU storage
        if self.data is not None:
            self.data[key] = data
            data = self.data[key]
        else:
            # Make sure data is an array
            if not isinstance(data,np.ndarray):
                data = np.array(data,dtype=self.dtype,copy=False)
            # Make sure data is big enough
            if data.size != size:
                data = np.resize(data,size).reshape(shape)

        # Set data (deferred)
        if self.base is None:
            self.set_data(data=data, offset=offset, copy=False)
        else:
            offset = self.offset + offset
            self.base.set_data(data=data, offset=offset, copy=False)


    def _parameterize(self):
        """ Paramaterize texture """

        if self._need_parameterization:
            if isinstance(self._interpolation,tuple):
                min_filter = self._interpolation[0]
                mag_filter = self._interpolation[1]
            else:
                min_filter = self._interpolation
                mag_filter = self._interpolation
            gl.glTexParameterf(self._target, gl.GL_TEXTURE_MIN_FILTER, min_filter)
            gl.glTexParameterf(self._target, gl.GL_TEXTURE_MAG_FILTER, mag_filter)

            if isinstance(self._wrapping,tuple):
                wrap_s = self._wrapping[0]
                wrap_t = self._wrapping[1]
            else:
                wrap_s = self._wrapping
                wrap_t = self._wrapping
            gl.glTexParameterf(self._target, gl.GL_TEXTURE_WRAP_S, wrap_s)
            gl.glTexParameterf(self._target, gl.GL_TEXTURE_WRAP_T, wrap_t)
        self._need_parameterization = True


    def _create(self):
        """ Create texture on GPU """

        log("GPU: Creating texture")
        self._handle = gl.glGenTextures(1)


    def _delete(self):
        """ Delete texture from GPU """

        log("GPU: Deleting texture")
        gl.glDeleteTextures([self._handle])


    def _activate(self):
        """ Activate texture on GPU """

        log("GPU: Activate texture")
        gl.glBindTexture(self.target, self._handle)
        if self._need_parameterization:
            self._parameterize()


    def _deactivate(self):
        """ Deactivate texture on GPU """

        log("GPU: Deactivate texture")
        gl.glBindTexture(self._target, 0)


# --------------------------------------------------------- Texture1D class ---
class Texture1D(Texture):
    """ """

    def __init__(self, data=None, shape=None, dtype=None,
                       store=True, copy=False, *args, **kwargs):
        """
        Initialize the texture.

        Parameters
        ----------

        data : np.ndarray
            Texture data (optional)

        dtype : np.dtype
            Texture data type (optional)

        shape : tuple of integers
            Texture shape

        store : boolean
           Indicate whether to use an intermediate CPU storage

        copy : boolean
           Indicate whether to use given data as CPU storage
        """

        # We don't want these parameters to be seen from outside (because they
        # are only used internally)
        offset     = kwargs.get("offset", None)
        base       = kwargs.get("base", None)
        resizeable = kwargs.get("resizeable", True)

        if data is not None:
            dtype = data.dtype
            shape = data.shape

        if dtype.fields:
            raise ValueError("Texture dtype cannot be structured")
        elif len(shape) < 1:
            raise ValueError("Too few dimensions for texture")
        elif len(shape) > 2:
            raise ValueError("Too many dimensions for texture")
        elif len(shape) == 1:
            if data is not None:
                data = data.reshape((shape[0],1))
            shape = (shape[0],1)
        elif len(shape) == 2:
            if shape[-1] > 4:
                raise ValueError("Too many channels for texture")

        Texture.__init__(self, data=data, shape=shape, dtype=dtype, base=base,
                         store=store, copy=copy, target=gl.GL_TEXTURE_1D, offset=offset)

        self._format = Texture._formats.get(self.shape[-1], None)
        if self._format is None:
            raise ValueError("Cannot convert data to texture")


    @property
    def width(self):
        """ Texture width """

        return self._shape[0]


    def _resize(self):
        """ Texture resize on GPU """

        log("GPU: Resizing texture(%s)"% (self.width))
        gl.glTexImage1D(self.target, 0, self._format, self.width,
                        0, self._format, self._gtype, None)


    def _update(self):
        """ Texture update on GPU """

        # We let base texture to handle all operations
        if self.base is not None:
            return

        if self._need_resize:
            self._resize()
            self._need_resize = False
        log("GPU: Updating texture (%d pending operation(s))" % len(self._pending_data))

        while self._pending_data:
            data, offset = self._pending_data.pop(0)
            if offset is None:
                x = 0
            else:
                x = offset[0]
            width = data.shape[0]
            gl.glTexSubImage1D(self.target, 0, x,
                               width, self._format, self._gtype, data)



# --------------------------------------------------------- Texture2D class ---
class Texture2D(Texture):
    """ """

    def __init__(self, data=None, shape=None, dtype=None,
                       store=True, copy=False, *args, **kwargs):
        """
        Initialize the texture.

        Parameters
        ----------

        data : np.ndarray
            Texture data (optional)

        dtype : np.dtype
            Texture data type (optional)

        shape : tuple of integers
            Texture shape

        store : boolean
           Indicate whether to use an intermediate CPU storage

        copy : boolean
           Indicate whether to use given data as CPU storage
        """

        # We don't want these parameters to be seen from outside (because they
        # are only used internally)
        offset     = kwargs.get("offset", None)
        base       = kwargs.get("base", None)
        resizeable = kwargs.get("resizeable", True)

        if data is not None:
            dtype = data.dtype
            shape = data.shape

        if dtype.fields:
            raise ValueError("Texture dtype cannot be structured")
        elif len(shape) < 2:
            raise ValueError("Too few dimensions for texture")
        elif len(shape) > 3:
            raise ValueError("Too many dimensions for texture")
        elif len(shape) == 2:
            if data is not None:
                data = data.reshape((shape[0],shape[1],1))
            shape = (shape[0],shape[1],1)
        elif len(shape) == 3:
            if shape[-1] > 4:
                raise ValueError("Too many channels for texture")

        Texture.__init__(self, data=data, shape=shape, dtype=dtype, base=base,
                         store=store, copy=copy, target=gl.GL_TEXTURE_2D, offset=offset)

        self._format = Texture._formats.get(self.shape[-1], None)
        if self._format is None:
            raise ValueError("Cannot convert data to texture")


    @property
    def height(self):
        """ Texture height """

        return self._shape[0]


    @property
    def width(self):
        """ Texture width """

        return self._shape[1]


    def _resize(self):
        """ Texture resize on GPU """

        log("GPU: Resizing texture(%sx%s)"% (self.width,self.height))
        gl.glTexImage2D(self.target, 0, self._format, self.width, self.height,
                        0, self._format, self._gtype, None)


    def _update(self):
        """ Texture update on GPU """

        # We let base texture to handle all operations
        if self.base is not None:
            return

        if self._need_resize:
            self._resize()
            self._need_resize = False
        log("GPU: Updating texture (%d pending operation(s))" % len(self._pending_data))

        while self._pending_data:
            data, offset = self._pending_data.pop(0)
            x, y = 0,0
            if offset is not None:
                y,x = offset[0], offset[1]
            width, height = data.shape[1],data.shape[0]
            gl.glTexSubImage2D(self.target, 0, x, y,
                               width, height, self._format, self._gtype, data)
