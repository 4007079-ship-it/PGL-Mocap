using UnrealBuildTool;

public class PGLMocapLiveLink : ModuleRules
{
	public PGLMocapLiveLink(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"LiveLinkInterface",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"InputCore",
			"Json",
			"Networking",
			"Sockets",
			"Slate",
			"SlateCore",
		});
	}
}
