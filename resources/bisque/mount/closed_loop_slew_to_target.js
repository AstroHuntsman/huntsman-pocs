/* Java Script */
Out = '';

sky6RASCOMTele.Abort();
ClosedLoopSlew.exec();

}
Out = JSON.stringify({
	"msg": "Closed loop slew complete",
    "success": true,
});


var Target = "$target";
var Out = "";
var err;

sky6StarChart.LASTCOMERROR = 0;

// Make sure the target is set
sky6StarChart.Find(Target);

err = sky6StarChart.LASTCOMERROR;
if (err != 0) {
    Out = Target + " not found.";

} else {

    // Check telescope is connected
    sky6RASCOMTele.Connect()
    if (sky6RASCOMTele.IsConnected == 0) {
        Out = "No connection to telescope";

    } else {

      // Check if the camera is connected
      err = ccdSoftCamera.Connect()
      if (err != 0) {
        Out = "No connection to camera";

      } else {

        // Prepare for closed loop slew
        sky6RASCOMTele.Asynchronous = $async;
        sky6RASCOMTele.Abort();

        // Execute closed loop slew
        ClosedLoopSlew.exec();

        Out = JSON.stringify({
        	"msg": 'Mount homed',
        	"success": true,
        });
      }
    }
}
