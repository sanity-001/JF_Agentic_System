"""
图像传感器处理器模块
包含ImageSensorProcessor主类，整合所有数据处理功能
"""
import os
import argparse
import numpy as np
import csv
import matplotlib.pyplot as plt

# 导入自定义模块
from .data_io import DataIO
from .image_processing import ImageProcessor
from .gaussian_fitting import fit_pixel_full, gaussian, gauss_erfc_model
from .gain_analysis import GainAnalyzer, compute_gainmap, compute_noisepeakmap
from .visualization import Visualizer
from scipy.optimize import curve_fit
from scipy.special import erfc

# 导入新模块
from ..core import (
    Config, get_logger, ProgressTracker,
    ImageSensorError, ProcessingError,
    timer, format_size, get_file_info
)


class ImageSensorProcessor:
    """图像传感器处理主类"""
    
    def __init__(self, enable_log_file: bool = True):
        self.data_io = DataIO()
        self.image_processor = ImageProcessor()
        self.gain_analyzer = GainAnalyzer()
        self.visualizer = Visualizer()
        
        # 启用自动日志文件记录
        self.logger = get_logger(auto_log_file=enable_log_file)
        
        # 使用配置类的默认参数
        self.default_file_path = Config.DEFAULT_INPUT_FILE
        self.default_baseline_file = Config.DEFAULT_BASELINE_FILE
        self.output_dir = Config.DEFAULT_OUTPUT_DIR

    def _load_baseline(self, baseline_path):
        """Load baseline data from .raw or .npy file.

        Returns numpy array or None if format is unrecognized.
        """
        if not baseline_path:
            return None
        if baseline_path.endswith('.raw'):
            print(f"  Reading baseline average from {baseline_path}...")
            baseline_data = self.data_io.read_average_frames(baseline_path)
            print(f"  Baseline stats: mean={baseline_data.mean():.2f}, std={baseline_data.std():.2f} ADU")
            return baseline_data
        elif baseline_path.endswith('.npy'):
            print(f"  Loading baseline file: {baseline_path}")
            baseline_data = np.load(baseline_path, allow_pickle=True)
            print(f"  Baseline stats: mean={baseline_data.mean():.2f}, std={baseline_data.std():.2f} ADU")
            return baseline_data
        else:
            print(f"  Warning: unrecognized baseline format: {baseline_path}")
            print(f"  Supported formats: .raw or .npy")
            return None

    def process_all_frames(self, file_path, output_dir, baseline_file=None,
                          use_baseline=False, color_min=0, color_max=65535):
        """处理全部帧并保存为图像
        
        Args:
            file_path: 输入文件路径
            output_dir: 输出目录
            baseline_file: 基线文件路径（可选）
            use_baseline: 是否扣除基线
            color_min: 对比度最小值
            color_max: 对比度最大值
            
        Raises:
            FileNotFoundError: 输入文件不存在
            ProcessingError: 处理过程中发生错误
        """
        try:
            # 验证输入文件
            input_path = Config.validate_file_path(file_path)
            file_info = get_file_info(file_path)
            self.logger.info(f"处理文件: {file_info['name']} ({file_info['size_formatted']})")
            
            # 创建输出目录
            Config.ensure_output_dir(output_dir)
            Config.ensure_output_dir(f"{output_dir}/gray-image")
            Config.ensure_output_dir(f"{output_dir}/Pseudo-color")
            
            # 读取基线
            baseline_data = None
            if use_baseline and baseline_file:
                try:
                    baseline_path = Config.validate_file_path(baseline_file)
                    self.logger.info(f"加载基线文件: {baseline_path.name}")
                    with timer("基线数据加载"):
                        baseline_data = self.data_io.read_average_frames(baseline_file)
                except FileNotFoundError:
                    self.logger.warning(f"基线文件未找到: {baseline_file}，将不扣除基线")
                    use_baseline = False
            
            # 计算总帧数
            size = os.path.getsize(file_path)
            total_frames = size // self.data_io.frame_size
            frames_to_process = min(Config.MAX_FRAMES_TO_PROCESS, total_frames)
            
            self.logger.info(f"文件包含 {total_frames} 帧，将处理前 {frames_to_process} 帧")
            
            # 使用进度跟踪器
            tracker = ProgressTracker(frames_to_process, "处理帧")
            
            with timer("帧处理"):
                for frame_idx in range(frames_to_process):
                    try:
                        img_array, frame_number = self.data_io.read_frame(file_path, frame_idx)
                        
                        # 扣除基线
                        if use_baseline and baseline_data is not None:
                            img_array = self.image_processor.subtract_baseline(img_array, baseline_data)
                        
                        # 调整对比度并保存
                        img_clip = self.image_processor.adjust_contrast(img_array, color_min, color_max)
                        img_stretch = img_clip.astype(np.uint16)
                        
                        # 保存灰度图
                        gray_path = f"{output_dir}/gray-image/frame_{frame_idx:04d}_no_{frame_number}.png"
                        self.image_processor.save_as_png(img_stretch, gray_path)
                        
                        # 保存伪彩色图
                        import matplotlib.cm as cm
                        norm = self.image_processor.normalize_for_display(img_clip, color_min, color_max)
                        pseudo_color = cm.jet(norm)[:, :, :3]
                        pseudo_color_img = (pseudo_color * 255).astype(np.uint8)
                        pseudo_path = f"{output_dir}/Pseudo-color/frame_{frame_idx:04d}_no_{frame_number}_pseudo.png"
                        self.image_processor.save_as_png(pseudo_color_img, pseudo_path)
                        
                        tracker.update()
                        
                    except Exception as e:
                        self.logger.error(f"处理第 {frame_idx} 帧时出错: {e}")
                        continue
            
            tracker.finish()
            self.logger.info(f"处理完成，输出目录: {output_dir}")
            
        except FileNotFoundError as e:
            raise ProcessingError(f"文件未找到: {e}")
        except Exception as e:
            raise ProcessingError(f"处理帧时发生错误: {e}")
    
    def show_average_frames(self, file_path, start_frame, end_frame, 
                           baseline_file=None, use_baseline=False, output_dir=None,
                           color_min=0, color_max=16383, plot_hist=True):
        """显示并保存平均帧
        
        注意：如果使用基线扣除，会对每一帧扣除基线后再取平均
        
        Args:
            color_min: 对比度调整最小值（用于contrast stretch）
            color_max: 对比度调整最大值（用于contrast stretch）
        """
        if output_dir is None:
            output_dir = self.output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 读取基线数据
        baseline_data = None
        if use_baseline and baseline_file:
            baseline_data = self.data_io.read_average_frames(baseline_file)
        
        # 计算平均帧
        size = os.path.getsize(file_path)
        total_frames = size // self.data_io.frame_size
        
        if end_frame is None:
            end_frame = total_frames - 1
        
        frame_count = end_frame - start_frame + 1
        avg_img = None
        if use_baseline:
            avg_img_subtract = None
        
        for idx in range(frame_count):
            frame_idx = start_frame + idx
            img_array, _ = self.data_io.read_frame(file_path, frame_idx)

            # Accumulate frames
            if avg_img is None:
                avg_img = img_array.astype(np.float64)
            else:
                avg_img += img_array.astype(np.float64)
        
        # 计算平均
        if avg_img is not None:
            avg_img = avg_img / frame_count
        if use_baseline and baseline_data is not None:
            avg_img_subtract = avg_img - baseline_data
        
        # Save average image
        filename = os.path.splitext(os.path.basename(file_path))[0]

        np.save(os.path.join(output_dir, f"{filename}_avg_frames_{start_frame}_{end_frame}_baseline.npy"), avg_img)
        if use_baseline:
            np.save(os.path.join(output_dir, f"{filename}_avg_frames_{start_frame}_{end_frame}_baseline_subtracted.npy"), avg_img_subtract)
        
        # 获取原始数据范围
        img_min = np.percentile(avg_img, 0.1)
        print(f"Image min (0.1th percentile): {img_min}")
        img_max = np.percentile(avg_img, 99.9)
        print(f"Image max (99.9th percentile): {img_max}")
        if use_baseline:
            img_min_subtract = np.percentile(avg_img_subtract, 0.1)
            print(f"Image min baseline subtracted (0.1th percentile): {img_min_subtract}")
            img_max_subtract = np.percentile(avg_img_subtract, 99.9)
            print(f"Image max baseline subtracted (99.9th percentile): {img_max_subtract}")

        # 原始ADU标题
        title_original = f"Average of frames {start_frame} to {end_frame}"
        if use_baseline:
            title_original += " (Baseline Subtracted)"
        title_original += f" [Range: {img_min:.1f} - {img_max:.1f} ADU]"
        
        if plot_hist:
            hist_filename = os.path.splitext(os.path.basename(file_path))[0]
            self.visualizer.plot_histogram(avg_img, bins=100, integral=False, range_vals=(img_min, img_max),
                                          title=title_original, xlabel="ADU", ylabel="Counts",
                                          output_path=os.path.join(output_dir, f"{hist_filename}_avg_{start_frame}_{end_frame}_histogram.png"),
                                          color='blue', alpha=0.7, text_lines=True)
            if use_baseline:
                self.visualizer.plot_histogram(avg_img_subtract, bins=100, integral=False, range_vals=(img_min_subtract, img_max_subtract),
                                              title=title_original + " (Baseline Subtracted)", xlabel="ADU", ylabel="Counts",
                                              output_path=os.path.join(output_dir, f"{hist_filename}_avg_{start_frame}_{end_frame}_histogram_baseline_subtracted.png"),
                                              color='green', alpha=0.7, text_lines=True)
        
        # 保存原始ADU灰度图
        # 保存的文件名需要包含输入文件名信息以区分
        gray_filename = os.path.splitext(os.path.basename(file_path))[0]
        gray_path = os.path.join(output_dir, f"{gray_filename}_avg_{start_frame}_{end_frame}_gray.png")
        self.visualizer.plot_heatmap(avg_img, title=title_original, cmap='gray', 
                                     vmin=img_min, vmax=img_max,
                                     colorbar_label='ADU', output_path=gray_path)
        if use_baseline:
            self.visualizer.plot_heatmap(avg_img_subtract, title=title_original + " (Baseline Subtracted)", cmap='gray', 
                                         vmin=img_min_subtract, vmax=img_max_subtract,
                                         colorbar_label='ADU', output_path=os.path.join(output_dir, f"{gray_filename}_avg_{start_frame}_{end_frame}_gray_baseline_subtracted.png"))
        
        # 保存原始ADU伪彩色图
        pseudo_filename = os.path.splitext(os.path.basename(file_path))[0]
        pseudo_path = os.path.join(output_dir, f"{pseudo_filename}_avg_{start_frame}_{end_frame}_pseudo.png")
        self.visualizer.plot_heatmap(avg_img, title=title_original + " (Pseudo-color)", 
                                     cmap='jet', vmin=img_min, vmax=img_max,
                                     colorbar_label='ADU', output_path=pseudo_path)
        if use_baseline:
            self.visualizer.plot_heatmap(avg_img_subtract, title=title_original + " (Baseline Subtracted) (Pseudo-color)", 
                                         cmap='jet', vmin=img_min_subtract, vmax=img_max_subtract,
                                         colorbar_label='ADU', output_path=os.path.join(output_dir, f"{pseudo_filename}_avg_{start_frame}_{end_frame}_pseudo_baseline_subtracted.png"))
        
        # 如果指定了对比度拉伸，保存拉伸后的版本
        if color_min != 0 or color_max != 16383:
            # 进行对比度拉伸
            img_stretched = self.image_processor.adjust_contrast(avg_img_subtract if use_baseline else avg_img, color_min, color_max)
            
            # 拉伸后的数据范围
            stretch_min = float(np.nanmin(img_stretched))
            stretch_max = float(np.nanmax(img_stretched))
            
            # 拉伸后标题
            title_stretched = f"Average of frames {start_frame} to {end_frame} (Contrast Stretched {color_min}-{color_max})"
            if use_baseline:
                title_stretched += " (Baseline Subtracted)"
            title_stretched += f" [Range: {stretch_min:.1f} - {stretch_max:.1f} ADU]"
            
            # 保存拉伸后的灰度图
            gray_stretched_path = os.path.join(output_dir, f"{gray_filename}_avg_{start_frame}_{end_frame}_gray_stretched.png")
            self.visualizer.plot_heatmap(img_stretched, title=title_stretched, cmap='gray', 
                                         vmin=stretch_min, vmax=stretch_max,
                                         colorbar_label='ADU', output_path=gray_stretched_path)
            
            # 保存拉伸后的伪彩色图
            pseudo_stretched_path = os.path.join(output_dir, f"{pseudo_filename}_avg_{start_frame}_{end_frame}_pseudo_stretched.png")
            self.visualizer.plot_heatmap(img_stretched, title=title_stretched + " (Pseudo-color)", 
                                         cmap='jet', vmin=stretch_min, vmax=stretch_max,
                                         colorbar_label='ADU', output_path=pseudo_stretched_path)
        
        print(f"Saved average frames to {output_dir}")
    
    def compute_std_map(self, file_path, start_frame=0, end_frame=None,
                        baseline_file=None, use_baseline=False,
                        output_dir=None, save_npy=True, plot_heatmap=True, plot_histogram=True):
        """
        计算所有像素在时间序列上的标准差
        采用Welford在线算法，避免内存溢出
        """
        if output_dir is None:
            output_dir = self.output_dir
        os.makedirs(output_dir, exist_ok=True)

        # 1. 读取基线数据
        baseline_data = None
        if use_baseline and baseline_file:
            baseline_data = self.data_io.read_average_frames(baseline_file)
            self.logger.info(f"Loaded baseline data from {baseline_file}")
        
        # 2. 确定帧范围
        total_frames = os.path.getsize(file_path) // self.data_io.frame_size
        print(f"size: {os.path.getsize(file_path)}, total_frames: {total_frames}")
        if end_frame is None or end_frame >= total_frames:
            end_frame = total_frames - 1
        frame_count = end_frame - start_frame + 1
        print(f"end_frame: {end_frame}, frame_count: {frame_count}")
        self.logger.info(f"Computing std map for frames {start_frame} to {end_frame} (total {frame_count} frames)")

        # 3. Welford在线算法计算标准差
        n = 0
        mean_map = np.zeros(self.data_io.frame_shape, dtype=np.float64)
        M2_map = np.zeros(self.data_io.frame_shape, dtype=np.float64)

        for frame_idx in range(start_frame, end_frame + 1):
            img_array, _ = self.data_io.read_frame(file_path, frame_idx)

            if use_baseline and baseline_data is not None:
                img_array = self.image_processor.subtract_baseline(img_array, baseline_data)
            
            # 在线更新统计量
            n += 1
            delta = img_array - mean_map
            mean_map += delta / n
            M2_map += delta * (img_array - mean_map)

            if (frame_idx - start_frame + 1) % 1000 == 0:
                self.logger.info(f"Processed {frame_idx - start_frame + 1} / {frame_count}")
        
        std_map = np.sqrt(M2_map / n) if n > 1 else np.zeros_like(mean_map)

        # 4. 保存.npy文件
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        if save_npy:
            npy_path = os.path.join(output_dir, f"{base_name}_std_map_{start_frame}_{end_frame}.npy")
            np.save(npy_path, std_map)
            self.logger.info(f"Saved std map to {npy_path}")
        
        # 5. 绘制并保存热力图
        if plot_heatmap:
            vmin = np.percentile(std_map, 1)
            vmax = np.percentile(std_map, 99)
            heatmap_title = f"Standard Deviation Map \n(Frames {start_frame}-{end_frame})"
            if use_baseline:
                heatmap_title += " (Baseline Subtracted)"
            heatmap_filename = os.path.join(output_dir, f"{base_name}_std_map_{start_frame}_{end_frame}_heatmap.png")

            self.visualizer.plot_heatmap(std_map, title=heatmap_title, cmap='jet',
                                            vmin=vmin, vmax=vmax, colorbar_label='Std Dev (ADU)', output_path=heatmap_filename)
            self.logger.info(f"Saved std map heatmap to {heatmap_filename}")
        
        # 6. 绘制并保存标准差分布直方图
        if plot_histogram:
            hist_title = f"Standard Deviation Distribution \n(Frames {start_frame}-{end_frame})"
            if use_baseline:
                hist_title += " (Baseline Subtracted)"
            hist_filename = os.path.join(output_dir, f"{base_name}_std_map_{start_frame}_{end_frame}_histogram.png")

            self.visualizer.plot_histogram(std_map.flatten(), bins=100, integral=False,
                                            title=hist_title, xlabel="Std Dev (ADU)", ylabel="Counts",
                                            output_path=hist_filename, color='purple', alpha=0.7, text_lines=True)
            self.logger.info(f"Saved std map histogram to {hist_filename}")
        
        # 7. 输出统计信息
        stats = {
            'mean_std': float(np.mean(std_map)),
            'median_std': float(np.median(std_map)),
            'min_std': float(np.min(std_map)),
            'max_std': float(np.max(std_map)),
            'p95': float(np.percentile(std_map, 95)),
            'frame_used': frame_count
        }
        self.logger.info(
            f"Std Map Stats: mean={stats['mean_std']:.2f}, median={stats['median_std']:.2f}, "
            f"min={stats['min_std']:.2f}, max={stats['max_std']:.2f}, 95th percentile={stats['p95']:.2f}"
        )

        return std_map, stats

    
    def _save_pixel_series(self, out_dir, label, rx, cx, raw_series, sub_series, baseline_series):
        """Save pixel time series data to .npy files."""
        for suffix, data in [("adu_raw", raw_series), ("adu", sub_series)]:
            path = os.path.join(out_dir, f"{label}_pixel_{rx}_{cx}_{suffix}.npy")
            np.save(path, data)
            print(f"Saved ADU series -> {path}")
        baseline_path = os.path.join(out_dir, f"baseline_pixel_{rx}_{cx}.npy")
        np.save(baseline_path, baseline_series)
        print(f"Saved baseline pixel series -> {baseline_path}")

    def _plot_pixel_histograms(self, out_dir, label, rx, cx, frame_count,
                                raw_series, sub_series, baseline_series, bins):
        """Plot raw, baseline-subtracted, and baseline histograms."""
        baseline_frames = len(baseline_series)
        configs = [
            (raw_series, f"{label}_hist_{rx}_{cx}_raw.png", True,
             f"Pixel histogram at ({rx},{cx}) — {label} (n={frame_count}) (No Baseline Subtracted)"),
            (sub_series, f"{label}_hist_{rx}_{cx}.png", False,
             f"Pixel histogram at ({rx},{cx}) — {label} (n={frame_count})"),
            (baseline_series, f"baseline_hist_{rx}_{cx}.png", True,
             f"Baseline Pixel Distribution at ({rx},{cx}) (n={baseline_frames})"),
        ]
        for data, filename, integral, title in configs:
            self.visualizer.plot_histogram(
                data, bins=bins, integral=integral,
                title=title, xlabel="ADU", ylabel="Counts",
                output_path=os.path.join(out_dir, filename)
            )

    def _fit_and_plot_baseline(self, out_dir, label, rx, cx, baseline_series):
        """Fit Gaussian to baseline data and save plot."""
        range_vals = (np.nanmin(baseline_series), np.nanmax(baseline_series))
        if range_vals[1] - range_vals[0] < 10:
            bins_integral = np.arange(range_vals[0] - 50, range_vals[1] + 50, 1)
        else:
            bins_integral = np.arange(range_vals[0] - 0.5, range_vals[1] + 1.5, 1)

        hist, edges = np.histogram(baseline_series, bins=bins_integral)
        centers = 0.5 * (edges[:-1] + edges[1:])
        fit_path = os.path.join(out_dir, f"{label}_baseline_fit_{rx}_{cx}.png")

        try:
            A0 = float(hist.max())
            mu0 = centers[np.argmax(hist)]
            sigma0 = (range_vals[1] - range_vals[0]) / 6
            popt, pcov = curve_fit(
                gaussian, centers, hist,
                p0=[A0, mu0, sigma0],
                bounds=([0.0, range_vals[0], 1e-2],
                        [np.inf, range_vals[1], range_vals[1] - range_vals[0]]),
                maxfev=Config.MAXFEV_DEFAULT
            )
            perr = np.sqrt(np.diag(pcov)) if pcov is not None else np.full_like(popt, np.nan, dtype=float)
            self.visualizer.plot_gaussian_fit(
                centers, hist, popt, perr,
                title=f"Baseline Peak Fit at ({rx},{cx}) — {label}",
                xlabel="ADU", ylabel="Counts", output_path=fit_path,
                x_range=range_vals
            )
            print(f"  Saved baseline fit: {fit_path}")
        except Exception as e:
            print(f"  Warning: baseline visualization fit failed: {e}")

    def _plot_noise_peak_fit(self, out_dir, label, rx, cx, series, noise_peak,
                               noise_range, bins_noise):
        """Fit and plot Gaussian to noise peak region."""
        if series is None:
            return
        mask = (series >= noise_range[0]) & (series <= noise_range[1])
        noise_data = series[mask]
        if noise_data.size < 10:
            return

        hist, edges = np.histogram(noise_data, bins=bins_noise, range=noise_range)
        centers = 0.5 * (edges[:-1] + edges[1:])
        noise_path = os.path.join(out_dir, f"{label}_noise_fit_{rx}_{cx}.png")

        try:
            A0 = float(hist.max())
            sigma0 = (noise_range[1] - noise_range[0]) / 6
            popt, pcov = curve_fit(
                gaussian, centers, hist, p0=[A0, noise_peak, sigma0],
                bounds=([0.0, noise_range[0], 1e-2],
                        [np.inf, noise_range[1], noise_range[1] - noise_range[0]]),
                maxfev=Config.MAXFEV_DEFAULT
            )
            perr = np.sqrt(np.diag(pcov)) if pcov is not None else np.full_like(popt, np.nan, dtype=float)
            self.visualizer.plot_gaussian_fit(
                centers, hist, popt, perr,
                title=f"Noise Peak Fit at ({rx},{cx}) — {label}",
                xlabel="ADU", ylabel="Counts", output_path=noise_path,
                x_range=noise_range
            )
            print(f"  Saved noise fit: {noise_path}")
        except Exception as e:
            print(f"  Warning: noise peak visualization fit failed: {e}")

    def _plot_ka_full_fit(self, out_dir, label, rx, cx, pixel_series, noise_peak,
                           signal_peak, ka_full_range, bins_full):
        """Fit Gaussian+erfc to K-alpha peak and save plot."""
        data_shifted = pixel_series - noise_peak
        corrected_range = (ka_full_range[0] - noise_peak, ka_full_range[1] - noise_peak)
        mask = (data_shifted >= corrected_range[0]) & (data_shifted <= corrected_range[1])
        data_for_hist = data_shifted[mask]

        if data_for_hist.size < 10:
            return

        hist, edges = np.histogram(data_for_hist, bins=bins_full, range=corrected_range)
        centers = 0.5 * (edges[:-1] + edges[1:])
        ka_path = os.path.join(out_dir, f"{label}_Ka_full_fit_{rx}_{cx}.png")

        try:
            A0 = float(hist.max())
            mu0 = signal_peak
            sigma0 = 5.0
            A_erfc0 = max(1.0, 0.5 * A0)
            lb = [0.0, mu0 - max(50.0, sigma0 * 5.0), 1e-2, 0.0]
            ub = [np.inf, mu0 + max(50.0, sigma0 * 5.0),
                  corrected_range[1] - corrected_range[0], np.inf]
            popt, pcov = curve_fit(
                gauss_erfc_model, centers, hist,
                p0=[A0, mu0, sigma0, A_erfc0], bounds=(lb, ub), maxfev=Config.MAXFEV_FULL
            )
            perr = np.sqrt(np.diag(pcov)) if pcov is not None else np.full_like(popt, np.nan, dtype=float)
            self.visualizer.plot_gauss_erfc_fit(
                centers, hist, popt, perr, peak_x=signal_peak,
                title=f"K-alpha Peak Full Fit at ({rx},{cx}) — {label}",
                xlabel="ADU (shifted)", ylabel="Counts",
                output_path=ka_path, x_range=corrected_range
            )
            print(f"  Saved K-alpha full fit: {ka_path}")
        except Exception as e:
            print(f"  Warning: visualization fit failed: {e}")

    def fit_pixel_histogram(self, file_path, baseline_file, rx, cx, 
                           start_frame, end_frame, out_dir, bins=200,
                           hist_range=(100.0, 500.0), fit_gaussian=0,
                           noise_range=(-100.0, 100.0), ka_gauss_range=(280.0, 380.0),
                           ka_full_range=(100.0, 500.0), bins_noise=50, 
                           bins_gauss=50, bins_full=100, use_raw_for_noise=False):
        """对指定像素进行直方图拟合
        
        参数:
            use_raw_for_noise: 如果为True，使用扣除基线后的带光数据本身拟合噪声峰（在噪声范围如-100到100内）；
                              如果为False（默认），使用基线文件数据拟合噪声峰
        """
        os.makedirs(out_dir, exist_ok=True)

        # Load all pixel data
        baseline_data = self.data_io.read_average_frames(baseline_file)
        pixel_series_raw = self.data_io.read_pixel_series(file_path, rx, cx, start_frame, end_frame, None)
        pixel_series = self.data_io.read_pixel_series(file_path, rx, cx, start_frame, end_frame, baseline_data)
        baseline_pixel_series = self.data_io.read_pixel_series(baseline_file, rx, cx, 0, -1, None)

        label = f"frames_{start_frame}_{end_frame}"
        frame_count = end_frame - start_frame + 1

        # Save and plot data
        self._save_pixel_series(out_dir, label, rx, cx, pixel_series_raw, pixel_series, baseline_pixel_series)
        self._plot_pixel_histograms(out_dir, label, rx, cx, frame_count,
                                     pixel_series_raw, pixel_series, baseline_pixel_series, bins)
        self._fit_and_plot_baseline(out_dir, label, rx, cx, baseline_pixel_series)

        if fit_gaussian != 1:
            return

        print(f"Performing peak fitting for {label}...")
        if use_raw_for_noise:
            print("  Fitting noise peak from baseline-subtracted signal data...")
        else:
            print("  Fitting noise peak from baseline file data...")
            if baseline_pixel_series is None:
                print("  Error: cannot read baseline pixel series")
                return

        result = fit_pixel_full(
            pixel_series, gauss_guess=None, full_range=ka_full_range,
            bins=bins_full, sub_range=ka_gauss_range, only_gaussian=False,
            noise_range=noise_range, return_details=True,
            use_raw_for_noise=use_raw_for_noise, baseline_series=baseline_pixel_series
        )
        noise_peak, signal_peak, gain = result

        print(f"  Fit results:")
        print(f"    Noise peak: {noise_peak:.2f} ADU")
        print(f"    Signal peak: {signal_peak:.2f} ADU")
        print(f"    Gain: {gain:.4f} ADU/keV")

        if np.isnan(noise_peak):
            if not np.isnan(gain):
                print(f"  No noise/signal peak returned, using gain value = {gain:.4f} ADU/keV")
            else:
                print("  Noise peak fitting failed, no gain value obtained")
            return

        print(f"  Noise peak fit successful: mu = {noise_peak:.2f} ADU")

        # Plot noise peak fit
        noise_plot_series = pixel_series if use_raw_for_noise else (baseline_pixel_series - np.mean(baseline_pixel_series))
        self._plot_noise_peak_fit(out_dir, label, rx, cx, noise_plot_series,
                                   noise_peak, noise_range, bins_noise)

        if np.isnan(signal_peak):
            print("  Signal peak fitting failed")
            return

        # Plot K-alpha full fit
        print(f"  Signal peak fit successful: position = {signal_peak:.2f} ADU (noise-subtracted)")
        print(f"  Gain = {gain:.4f} ADU/keV")
        self._plot_ka_full_fit(out_dir, label, rx, cx, pixel_series, noise_peak,
                                signal_peak, ka_full_range, bins_full)

        data_source = "signal data" if use_raw_for_noise else "baseline data"
        print(f"  Fit summary:")
        print(f"    Noise fit data source: {data_source}")
        print(f"    Noise peak: mu = {noise_peak:.2f} ADU")
        print(f"    Signal peak: {signal_peak:.4f} ADU (noise-subtracted)")
        print(f"    Gain = {gain:.4f} ADU/keV")
    
    def compute_gain_map(self, raw_path, out_dir, use_raw_for_noise=False, **kwargs):
        """计算增益图
        
        Args:
            raw_path: 原始RAW文件路径
            out_dir: 输出目录
            use_raw_for_noise: 控制噪声峰拟合的数据源
                              - True: 使用扣除基线后的带光数据拟合噪声峰（在-100~100范围）
                              - False（默认）: 使用基线raw文件数据拟合噪声峰
                              注：无论选择哪个数据源，都会拟合噪声峰并平移，最终在扣除基线的带光数据上拟合信号峰
            **kwargs: 其他参数传递给compute_gainmap（如baseline_memmap, bins, hist_range等）
                
        Returns:
            gain_map: 计算得到的增益图
        """
        # 使用data_io的make_memmap_from_raw方法
        return compute_gainmap(
            raw_path, out_dir,
            make_memmap_func=self.data_io.make_memmap_from_raw,
            use_raw_for_noise=use_raw_for_noise,
            **kwargs
        )
    
    def compute_noise_peak_map(self, raw_path, out_dir, use_raw_for_noise=False, **kwargs):
        """计算噪声峰图
        
        Args:
            raw_path: 原始RAW文件路径
            out_dir: 输出目录
            use_raw_for_noise: 控制噪声峰拟合的数据源
                              - True: 使用扣除基线后的带光数据拟合噪声峰（在-100~100范围）
                              - False（默认）: 使用基线raw文件数据拟合噪声峰
        """
        # 使用data_io的make_memmap_from_raw方法
        return compute_noisepeakmap(
            raw_path, out_dir,
            make_memmap_func=self.data_io.make_memmap_from_raw,
            use_raw_for_noise=use_raw_for_noise,
            **kwargs
        )
    
    def analyze_gain_comparison(self, gain_left_path, gain_right_path,
                               origin_gain_path, adu_left_path, adu_right_path,
                               output_dir):
        """分析增益图对比"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 加载数据
        gain_left = np.load(gain_left_path)
        gain_right = np.load(gain_right_path)
        origin_gainmap = np.load(origin_gain_path)
        adu_left = np.load(adu_left_path)
        adu_right = np.load(adu_right_path)
        
        # 拼接完整增益图
        all_gain = self.gain_analyzer.merge_left_right_maps(gain_left, gain_right)
        all_adu = self.gain_analyzer.merge_left_right_maps(adu_left, adu_right)

        # 可视化左面板ADU图
        self.visualizer.plot_heatmap(
            self.image_processor.nan_to_num(adu_left), title="ADU Map Left Panel",
            cmap='viridis', vmin=0, vmax=250,
            colorbar_label='ADU',
            output_path=os.path.join(output_dir, "adu_map_left.png")
        )

        # 可视化右面板ADU图
        self.visualizer.plot_heatmap(
            self.image_processor.nan_to_num(adu_right), title="ADU Map Right Panel",
            cmap='viridis', vmin=0, vmax=250,
            colorbar_label='ADU',
            output_path=os.path.join(output_dir, "adu_map_right.png")
        )

        # 可视化全面板增益图
        self.visualizer.plot_heatmap(
            all_gain, title="Gain Map Full Sensor",
            cmap='viridis', vmin=35, vmax=45,
            colorbar_label='Gain [ADU/keV]',
            output_path=os.path.join(output_dir, "gain_map_full.png")
        )

        # 计算左面板光子能量
        origin_photon_energy_left = self.gain_analyzer.compute_photon_energy(adu_left, origin_gainmap)
        photon_energy_left = self.gain_analyzer.compute_photon_energy(adu_left, gain_left)

        # 计算右面板光子能量
        origin_photon_energy_right = self.gain_analyzer.compute_photon_energy(adu_right, origin_gainmap)
        photon_energy_right = self.gain_analyzer.compute_photon_energy(adu_right, gain_right)
    
        # 计算全面板光子能量
        origin_photon_energy = self.gain_analyzer.compute_photon_energy(all_adu, origin_gainmap)
        photon_energy = self.gain_analyzer.compute_photon_energy(all_adu, all_gain)
        
        # 可视化对比左面板光子能量图
        self.visualizer.plot_side_by_side(
            origin_photon_energy_left, photon_energy_left,
            title1="Photon Energy Left (Original Gain)",
            title2="Photon Energy Left (New Gain)",
            cmap='viridis', vmin=0.8, vmax=2.2,
            colorbar_label='Photon Energy',
            output_path=os.path.join(output_dir, "photon_energy_left_comparison.png")
        )

        # 可视化对比右面板光子能量图
        self.visualizer.plot_side_by_side(
            origin_photon_energy_right, photon_energy_right,
            title1="Photon Energy Right (Original Gain)",
            title2="Photon Energy Right (New Gain)",
            cmap='viridis', vmin=0.8, vmax=2.2,
            colorbar_label='Photon Energy',
            output_path=os.path.join(output_dir, "photon_energy_right_comparison.png")
        )

        # 可视化对比全面板光子能量图
        self.visualizer.plot_side_by_side(
            origin_photon_energy, photon_energy,
            title1="Photon Energy (Original Gain)",
            title2="Photon Energy (New Gain)",
            cmap='viridis', vmin=0.8, vmax=2.2,
            colorbar_label='Photon Energy',
            output_path=os.path.join(output_dir, "photon_energy_comparison.png")
        )
        
        # 计算相对变化
        gain_change_map = self.gain_analyzer.relative_change_map(origin_gainmap, all_gain)
        
        # 绘制相对变化图
        self.visualizer.plot_relative_change(
            gain_change_map, 
            title='Relative Change in Gain Map (%)',
            output_path=os.path.join(output_dir, "gain_relative_change.png")
        )

        # 绘制相对变化直方图
        self.visualizer.plot_relative_change_histogram(
            gain_change_map,
            bins=100,
            title='Histogram of Relative Gain Change (%)',
            output_path=os.path.join(output_dir, "gain_relative_change_histogram.png")
        )
        
        # 标记大变化
        for threshold in [2.0, 3.0, 4.0]:
            marked = self.gain_analyzer.mark_large_changes(gain_change_map, threshold=threshold)
            masked_change = np.where(marked == 1, gain_change_map, 0)
            self.visualizer.plot_relative_change(
                masked_change,
                title=f'Masked Relative Change (>{threshold}%)',
                output_path=os.path.join(output_dir, f"gain_change_masked_{threshold}pct.png")
            )
        
        # 绘制子图分析
        self.visualizer.plot_gain_submaps(gain_change_map, output_dir=output_dir)
        
        print(f"Gain analysis completed. Results saved to {output_dir}")
    
    def show_gain_map_from_frame(self, file_path, frame_idx, out_dir=None):
        """从帧中提取并显示gain map"""
        if out_dir is None:
            out_dir = self.output_dir
        os.makedirs(out_dir, exist_ok=True)
        
        gain_img = self.data_io.read_gain_from_frame(file_path, frame_idx)
        
        # 保存CSV
        out_csv = os.path.join(out_dir, f"gain_frame_{frame_idx}.csv")
        np.savetxt(out_csv, gain_img, fmt='%d', delimiter=',')
        print(f"Saved gain CSV -> {out_csv}")
        
        # 统计
        counts = np.bincount(gain_img.ravel(), minlength=4)
        total = counts.sum()
        print("Gain code counts:")
        for code in range(4):
            print(f"  code {code}: {counts[code]} pixels ({counts[code]/total*100.0:.2f}%)")
        
        # 可视化
        out_png = os.path.join(out_dir, f"gain_heatmap_frame_{frame_idx}.png")
        self.visualizer.plot_gain_heatmap(gain_img, frame_idx, output_path=out_png)
    
    def parse_arguments(self):
        """解析命令行参数"""
        parser = argparse.ArgumentParser(description='图像传感器数据处理工具')
        
        # 基本参数
        parser.add_argument('--input', '-i', type=str, default=self.default_file_path,
                          help='输入原始数据文件路径')
        parser.add_argument('--baseline', '-b', type=str, default=self.default_baseline_file,
                          help='基线数据文件路径')
        parser.add_argument('--output', '-o', type=str, default=self.output_dir,
                          help='输出目录')
        
        # 处理模式
        parser.add_argument('--mode', '-m', type=int, 
                          choices=[1, 2, 3, 4, 5, 6, 7], required=True,
                          help='处理模式: 1-处理全部帧 2-显示平均帧 3-像素直方图拟合 4-计算增益图 5-增益图对比分析 6-噪声峰拟合 7-标准差图分析')
        
        # 基线和对比度参数
        parser.add_argument('--use-baseline', '-ub', action='store_true',
                          help='是否扣除基线数据')
        parser.add_argument('--color-min', '-cmin', type=int, default=0,
                          help='对比度调整最小值')
        parser.add_argument('--color-max', '-cmax', type=int, default=16383,
                          help='对比度调整最大值')
        
        # 帧选择参数
        parser.add_argument('--start-frame', '-sf', type=int, default=0,
                          help='起始帧号')
        parser.add_argument('--end-frame', '-ef', type=int, default=None,
                          help='结束帧号')
        
        # 像素坐标参数（mode 3）
        parser.add_argument('--rx', type=int, default=300,
                          help='像素行坐标 (0-based)')
        parser.add_argument('--cx', type=int, default=300,
                          help='像素列坐标 (0-based)')
        
        # 拟合参数（mode 3）
        parser.add_argument('--bins', type=int, default=100,
                          help='直方图bins数量')
        parser.add_argument('--fit-gaussian', '-fg', type=int, default=0,
                          help='是否进行高斯拟合: 0-否 1-是')
        parser.add_argument('--use-raw-for-noise', '-urn', action='store_true',
                          help='使用扣除基线后的带光数据拟合噪声峰（默认使用基线文件数据拟合）')
        
        # 增益图计算参数（mode 4）
        parser.add_argument('--block-width', type=int, default=64,
                          help='列块宽度')
        parser.add_argument('--full-fit', action='store_true',
                          help='启用完整拟合')
        parser.add_argument('--only-gaussian', action='store_true',
                          help='仅使用单高斯拟合')
        
        # 增益图对比参数（mode 5）
        parser.add_argument('--gain-left', type=str,
                          help='左增益图路径')
        parser.add_argument('--gain-right', type=str,
                          help='右增益图路径')
        parser.add_argument('--origin-gain', type=str,
                          help='原始增益图路径')
        parser.add_argument('--adu-left', type=str,
                          help='左ADU图路径')
        parser.add_argument('--adu-right', type=str,
                          help='右ADU图路径')
        
        return parser.parse_args()
    
    def run_with_args(self):
        """使用命令行参数运行"""
        args = self.parse_arguments()
        self.output_dir = args.output
        
        if args.mode == 1:
            # 处理全部帧
            print(f"Mode 1: 处理全部帧")
            self.process_all_frames(
                args.input, args.output, args.baseline,
                args.use_baseline, args.color_min, args.color_max
            )
        
        elif args.mode == 2:
            # Display average frames
            if args.end_frame is None or args.end_frame <= args.start_frame:
                print("Error: end_frame must be specified and greater than start_frame")
                return
            print(f"Mode 2: 显示平均帧 {args.start_frame}-{args.end_frame}")
            self.show_average_frames(
                args.input, args.start_frame, args.end_frame,
                args.baseline, args.use_baseline, args.output,
                args.color_min, args.color_max
            )
        
        elif args.mode == 3:
            # Pixel histogram fitting
            if args.end_frame is None or args.end_frame <= args.start_frame:
                print("Error: end_frame must be specified and greater than start_frame")
                return
            print(f"Mode 3: 像素直方图拟合 ({args.rx}, {args.cx})")
            if args.use_raw_for_noise:
                print("  使用扣除基线后的带光数据拟合噪声峰")
            else:
                print("  使用基线文件数据拟合噪声峰")
            self.fit_pixel_histogram(
                args.input, args.baseline, args.rx, args.cx,
                args.start_frame, args.end_frame, args.output,
                bins=args.bins, fit_gaussian=args.fit_gaussian,
                use_raw_for_noise=args.use_raw_for_noise
            )
        
        elif args.mode == 4:
            # 计算增益图
            print(f"Mode 4: 计算增益图")
            
            baseline_data = self._load_baseline(args.baseline) if args.use_baseline else None

            self.compute_gain_map(
                args.input, args.output,
                block_width=args.block_width,
                bins=args.bins,
                use_baseline=args.use_baseline,
                baseline_memmap=baseline_data,
                full_fit=args.full_fit,
                only_gaussian=args.only_gaussian,
                use_raw_for_noise=args.use_raw_for_noise
            )
        
        elif args.mode == 5:
            # 增益图对比分析
            if not all([args.gain_left, args.gain_right, args.origin_gain,
                       args.adu_left, args.adu_right]):
                print("错误: Mode 5 需要指定所有增益图和ADU图路径")
                return
            print(f"Mode 5: 增益图对比分析")
            self.analyze_gain_comparison(
                args.gain_left, args.gain_right, args.origin_gain,
                args.adu_left, args.adu_right, args.output
            )

        elif args.mode == 6:
            # 噪声峰均值图
            print(f"Mode 6: 计算噪声峰均值图")

            baseline_data = self._load_baseline(args.baseline) if args.use_baseline else None

            self.compute_noise_peak_map(
                args.input, args.output,
                block_width=args.block_width,
                bins=args.bins,
                use_baseline=args.use_baseline,
                baseline_memmap=baseline_data,
                full_fit=args.full_fit,
                use_raw_for_noise=args.use_raw_for_noise
            )
        elif args.mode == 7:
            self.compute_std_map(
                file_path=args.input, 
                output_dir=args.output,
                start_frame=args.start_frame,
                end_frame=args.end_frame,
                baseline_file=args.baseline,
                use_baseline=args.use_baseline,
                save_npy=True,
                plot_heatmap=True,
                plot_histogram=True
            )
