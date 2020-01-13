import torch.nn as nn

from monai.networks.layers.convolutions import Convolution, ResidualUnit
from monai.networks.layers.simplelayers import SkipConnection
from monai.networks.utils import predict_segmentation
from monai.utils import export
from monai.utils.aliases import alias


@export("monai.networks.nets")
@alias("Unet", "unet")
class UNet(nn.Module):

    def __init__(self,
                 dimensions,
                 in_channels,
                 num_classes,
                 channels,
                 strides,
                 kernel_size=3,
                 up_kernel_size=3,
                 num_res_units=0,
                 instance_norm=True,
                 dropout=0):
        super().__init__()
        assert len(channels) == (len(strides) + 1)
        self.dimensions = dimensions
        self.in_channels = in_channels
        self.num_classes = num_classes
        self.channels = channels
        self.strides = strides
        self.kernel_size = kernel_size
        self.up_kernel_size = up_kernel_size
        self.num_res_units = num_res_units
        self.instance_norm = instance_norm
        self.dropout = dropout

        def _create_block(inc, outc, channels, strides, is_top):
            """
            Builds the UNet structure from the bottom up by recursing down to the bottom block, then creating sequential
            blocks containing the downsample path, a skip connection around the previous block, and the upsample path.
            """
            c = channels[0]
            s = strides[0]

            if len(channels) > 2:
                subblock = _create_block(c, c, channels[1:], strides[1:], False)  # continue recursion down
                upc = c * 2
            else:
                # the next layer is the bottom so stop recursion, create the bottom layer as the sublock for this layer
                subblock = self._get_bottom_layer(c, channels[1])
                upc = c + channels[1]

            down = self._get_down_layer(inc, c, s, is_top)  # create layer in downsampling path
            up = self._get_up_layer(upc, outc, s, is_top)  # create layer in upsampling path

            return nn.Sequential(down, SkipConnection(subblock), up)

        self.model = _create_block(in_channels, num_classes, self.channels, self.strides, True)

    def _get_down_layer(self, in_channels, out_channels, strides, is_top):
        if self.num_res_units > 0:
            return ResidualUnit(self.dimensions, in_channels, out_channels, strides, self.kernel_size, self.num_res_units,
                                self.instance_norm, self.dropout)
        else:
            return Convolution(self.dimensions, in_channels, out_channels, strides, self.kernel_size, self.instance_norm,
                               self.dropout)

    def _get_bottom_layer(self, in_channels, out_channels):
        return self._get_down_layer(in_channels, out_channels, 1, False)

    def _get_up_layer(self, in_channels, out_channels, strides, is_top):
        conv = Convolution(self.dimensions,
                           in_channels,
                           out_channels,
                           strides,
                           self.up_kernel_size,
                           self.instance_norm,
                           self.dropout,
                           conv_only=is_top and self.num_res_units == 0,
                           is_transposed=True)

        if self.num_res_units > 0:
            ru = ResidualUnit(self.dimensions,
                              out_channels,
                              out_channels,
                              1,
                              self.kernel_size,
                              1,
                              self.instance_norm,
                              self.dropout,
                              last_conv_only=is_top)
            return nn.Sequential(conv, ru)
        else:
            return conv

    def forward(self, x):
        x = self.model(x)
        return x, predict_segmentation(x)