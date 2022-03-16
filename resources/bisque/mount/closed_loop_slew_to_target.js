/* Java Script */

var Out = '';

sky6RASCOMTele.Asynchronous = $async;
sky6RASCOMTele.Abort();

ClosedLoopSlew.exec();

Out = JSON.stringify({
    "success": true
});
