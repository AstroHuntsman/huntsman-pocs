/* Java Script */
sky6Dome.Connect();
if (sky6Dome.IsConnected == 0) {
	Out = "Not connected"
} else {
	sky6Dome.Unpark();
	while (!sky6Dome.IsUnparkComplete) {
		sky6Web.Sleep(1000);
	}

	Out = JSON.stringify({
		"success": sky6Dome.IsUnparkComplete
	});
};
