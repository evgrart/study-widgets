using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("Study Timer")]
[assembly: AssemblyDescription("Учебный таймер — Study Timer")]
[assembly: AssemblyProduct("Study Timer")]
[assembly: AssemblyVersion("1.0.0.0")]

internal static class Launcher
{
    [STAThread]
    private static void Main()
    {
        string appRoot = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.GetFullPath(Path.Combine(appRoot, @"..\.venv\Scripts\pythonw.exe"));
        string script = Path.Combine(appRoot, "widget.py");
        try
        {
            if (!File.Exists(python) || !File.Exists(script))
                throw new FileNotFoundException("Не найден файл приложения или Python.");
            ProcessStartInfo info = new ProcessStartInfo(python, "\"" + script + "\"");
            info.WorkingDirectory = appRoot;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            Process.Start(info);
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "Учебный таймер", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
