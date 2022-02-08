import threading
from time import sleep, time
from typing import Dict, Optional

from StreamDeck import ImageHelpers
from StreamDeck.Devices.StreamDeck import StreamDeck

from streamdeck_ui.display.pipeline import Pipeline


class DisplayGrid:
    """
    A DisplayGrid is made up of a collection of pipelines, each processing
    filters for one individual button display.
    """

    def __init__(self, streamdeck: StreamDeck, fps: int = 25):
        # Reference to the actual device, used to update icons
        self.streamdeck = streamdeck
        # A dictionary of lists of pipelines. Each page has
        # a list, corresponding to each button.
        self.pages: Dict[int, Dict[int, Pipeline]] = {}
        self.current_page: int = -1
        self.pipeline_thread: Optional[threading.Thread] = None
        self.running = False
        self.fps = fps
        # Configure the maximum frame rate we want to achieve
        self.time_per_frame = 1 / 25

    def set_pipeline(self, page: int, button: int, pipeline: Pipeline):
        # TODO: Do we need to lock before manipulating?
        page_dict = self.pages.setdefault(page, {})
        page_dict.setdefault(button, pipeline)

    def get_pipeline(self, page: int, button: int) -> Pipeline:
        return self.pages[page][button]

    def _run(self):
        """Method that runs on background thread and updates the pipelines."""
        frames = 0
        start = time()
        last_page = -1
        execution_time = 0

        while self.running:
            current_time = time()
            page = self.pages[self.current_page]
            force_update = False

            if last_page != page:
                # When a page switch happen, force the pipelines to redraw so icons update
                force_update = True
                last_page = page

            for button, pipeline in page.items():

                # Process all the steps in the pipeline and return the resulting image
                image = pipeline.execute(current_time)

                # If none of the filters in the pipeline yielded a change, use
                # the last known result
                if force_update and image is None:
                    image = pipeline.last_result()

                if image:
                    # TODO: Potential improvement point - can we avoid native conversion?
                    image = ImageHelpers.PILHelper.to_native_format(self.streamdeck, image)
                    self.streamdeck.set_key_image(button, image)

            # Calculate how long we took to process the pipeline
            elapsed_time = time() - current_time
            execution_time += elapsed_time

            # Calculate how much we have to sleep between processing cycles to maintain the desired FPS
            # If we have less than 5ms left, don't bother sleeping, as the context switch and
            # overhead of sleeping/waking up is consumed
            time_left = self.time_per_frame - elapsed_time
            if time_left > 0.005:
                sleep(time_left)

            frames += 1
            if time() - start > 1.0:
                execution_time_ms = int(execution_time * 1000)
                print(f"FPS: {frames} Execution time: {execution_time_ms} ms Execution %: {int(execution_time_ms/1000 * 100)}")
                execution_time = 0
                frames = 0
                start = time()

    def set_page(self, page: int):
        """Switches to the given page. Pipelines for that page starts running,
        other page pipelines stop.

        Args:
            page (int): The page number to switch to.
        """
        self.current_page = page

    def start(self):
        if self.pipeline_thread is not None:
            self.running = False
            try:
                self.pipeline_thread.join()
            except RuntimeError:
                pass

        self.running = True
        self.pipeline_thread = threading.Thread(target=self._run)
        self.pipeline_thread.daemon = True
        self.pipeline_thread.start()

    def stop(self):

        if self.pipeline_thread is not None:
            self.running = False
            try:
                self.pipeline_thread.join()
            except RuntimeError:
                pass
